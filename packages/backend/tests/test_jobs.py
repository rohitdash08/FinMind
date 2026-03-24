"""Tests for the resilient background job system.

Covers: enqueue, execute, retry with backoff, dead-letter, manual retry,
job stats, and admin endpoints.
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("FLASK_ENV", "testing")

from app import create_app  # noqa: E402
from app.config import Settings  # noqa: E402
from app.extensions import db, redis_client  # noqa: E402
from app.models import BackgroundJob, JobStatus, User, Role  # noqa: E402
from app.services.jobs import (  # noqa: E402
    enqueue,
    execute_job,
    process_due_jobs,
    retry_dead_letter_job,
    get_job_stats,
    calculate_backoff,
    register_handler,
    _job_handlers,
)


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-jobs-32plus-chars-1234567890"


@pytest.fixture()
def app():
    settings = TestSettings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
    try:
        redis_client.flushdb()
    except Exception:
        pass
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        redis_client.flushdb()
    except Exception:
        pass


@pytest.fixture()
def app_ctx(app):
    """Push app context for service-level tests."""
    ctx = app.app_context()
    ctx.push()
    yield
    ctx.pop()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_auth(client):
    """Register an admin user and return auth header."""
    # Register
    r = client.post(
        "/auth/register",
        json={"email": "admin@test.com", "password": "adminpass123"},
    )
    assert r.status_code in (200, 201, 409)
    # Promote to admin directly via DB
    with client.application.app_context():
        user = User.query.filter_by(email="admin@test.com").first()
        user.role = Role.ADMIN.value
        db.session.commit()
    # Login
    r = client.post(
        "/auth/login",
        json={"email": "admin@test.com", "password": "adminpass123"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


@pytest.fixture()
def regular_auth(client):
    """Register a regular user and return auth header."""
    r = client.post(
        "/auth/register",
        json={"email": "user@test.com", "password": "userpass123"},
    )
    assert r.status_code in (200, 201, 409)
    r = client.post(
        "/auth/login",
        json={"email": "user@test.com", "password": "userpass123"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


# ─── Unit tests: service layer ────────────────────────────────────────────


def test_calculate_backoff():
    assert calculate_backoff(1).total_seconds() == 30
    assert calculate_backoff(2).total_seconds() == 120  # 2 min
    assert calculate_backoff(3).total_seconds() == 480  # 8 min
    assert calculate_backoff(4).total_seconds() == 1920  # 32 min


def test_enqueue_creates_pending_job(app_ctx):
    # Register a dummy handler
    @register_handler("test_job")
    def handle_test(payload):
        return {"ok": True}

    job = enqueue("test_job", payload={"key": "value"}, max_retries=2)
    assert job.id is not None
    assert job.status == JobStatus.PENDING
    assert job.job_type == "test_job"
    assert job.payload == {"key": "value"}
    assert job.max_retries == 2
    assert job.attempt == 0

    # Cleanup handler
    _job_handlers.pop("test_job", None)


def test_execute_success(app_ctx):
    @register_handler("success_job")
    def handle_success(payload):
        return {"result": "done"}

    job = enqueue("success_job", payload={"x": 1})
    success = execute_job(job)
    assert success is True
    assert job.status == JobStatus.SUCCESS
    assert job.attempt == 1
    assert job.result == {"result": "done"}
    assert job.completed_at is not None

    _job_handlers.pop("success_job", None)


def test_execute_retry_on_failure(app_ctx):
    call_count = 0

    @register_handler("flaky_job")
    def handle_flaky(payload):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Temporary failure")
        return {"ok": True}

    job = enqueue("flaky_job", max_retries=3)

    # First attempt: fails, schedules retry
    success = execute_job(job)
    assert success is False
    assert job.status == JobStatus.PENDING
    assert job.attempt == 1
    assert job.next_run_at > datetime.utcnow()
    assert "ConnectionError" in job.last_error

    # Second attempt: fails again
    job.next_run_at = datetime.utcnow()  # Force due
    success = execute_job(job)
    assert success is False
    assert job.attempt == 2

    # Third attempt: succeeds
    job.next_run_at = datetime.utcnow()
    success = execute_job(job)
    assert success is True
    assert job.status == JobStatus.SUCCESS

    _job_handlers.pop("flaky_job", None)


def test_execute_dead_letter_after_max_retries(app_ctx):
    @register_handler("always_fail")
    def handle_fail(payload):
        raise ValueError("Permanent failure")

    job = enqueue("always_fail", max_retries=2)

    # Attempt 1: retry
    execute_job(job)
    assert job.status == JobStatus.PENDING
    assert job.attempt == 1

    # Attempt 2: dead letter
    job.next_run_at = datetime.utcnow()
    execute_job(job)
    assert job.status == JobStatus.DEAD_LETTER
    assert job.attempt == 2
    assert job.completed_at is not None

    _job_handlers.pop("always_fail", None)


def test_execute_no_handler(app_ctx):
    job = enqueue("nonexistent_type")
    success = execute_job(job)
    assert success is False
    assert job.status == JobStatus.FAILED
    assert "No handler" in job.last_error


def test_process_due_jobs(app_ctx):
    @register_handler("batch_job")
    def handle_batch(payload):
        if payload.get("fail"):
            raise RuntimeError("batch fail")
        return {"ok": True}

    # Create 3 jobs: 2 succeed, 1 fails permanently
    now = datetime.utcnow()
    for i in range(2):
        enqueue("batch_job", payload={"i": i})
    enqueue("batch_job", payload={"fail": True}, max_retries=1)

    stats = process_due_jobs()
    assert stats["processed"] == 3
    assert stats["succeeded"] == 2
    assert stats["dead_lettered"] == 1

    _job_handlers.pop("batch_job", None)


def test_process_due_jobs_skips_not_due(app_ctx):
    @register_handler("future_job")
    def handle_future(payload):
        return {"ok": True}

    job = enqueue("future_job", delay_seconds=3600)
    stats = process_due_jobs()
    assert stats["processed"] == 0

    # Clean up
    job.delete()
    db.session.commit()
    _job_handlers.pop("future_job", None)


def test_retry_dead_letter(app_ctx):
    @register_handler("retry_dlq")
    def handle_retry(payload):
        raise ValueError("fail")

    job = enqueue("retry_dlq", max_retries=1)
    execute_job(job)
    assert job.status == JobStatus.DEAD_LETTER

    success = retry_dead_letter_job(job.id)
    assert success is True
    assert job.status == JobStatus.PENDING
    assert job.attempt == 0
    assert job.last_error is None
    assert job.completed_at is None

    _job_handlers.pop("retry_dlq", None)


def test_retry_non_dead_letter_returns_false(app_ctx):
    @register_handler("active_job")
    def handle_active(payload):
        return {"ok": True}

    job = enqueue("active_job")
    assert retry_dead_letter_job(job.id) is False  # PENDING, not DEAD_LETTER

    _job_handlers.pop("active_job", None)


def test_get_job_stats(app_ctx):
    @register_handler("stats_job")
    def handle_stats(payload):
        return {"ok": True}

    enqueue("stats_job")
    enqueue("stats_job")
    enqueue("stats_job")

    # Execute all
    process_due_jobs()

    stats = get_job_stats()
    assert stats["total"] == 3
    assert stats["by_status"].get("JobStatus.SUCCESS", 0) == 3
    assert stats["by_type"]["stats_job"] == 3

    _job_handlers.pop("stats_job", None)


# ─── Integration tests: admin API ─────────────────────────────────────────


def test_admin_job_stats(client, admin_auth):
    r = client.get("/admin/jobs/stats", headers=admin_auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "by_status" in data
    assert "by_type" in data
    assert "total" in data


def test_admin_list_jobs(client, admin_auth):
    r = client.get("/admin/jobs", headers=admin_auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "total" in data
    assert "jobs" in data


def test_admin_list_jobs_filter(client, admin_auth):
    r = client.get("/admin/jobs?status=DEAD_LETTER&limit=10", headers=admin_auth)
    assert r.status_code == 200


def test_admin_list_jobs_invalid_status(client, admin_auth):
    r = client.get("/admin/jobs?status=INVALID", headers=admin_auth)
    assert r.status_code == 400


def test_admin_get_job_not_found(client, admin_auth):
    r = client.get("/admin/jobs/99999", headers=admin_auth)
    assert r.status_code == 404


def test_admin_trigger_process(client, admin_auth):
    r = client.post("/admin/jobs/process", headers=admin_auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "processed" in data


def test_admin_delete_job_not_found(client, admin_auth):
    r = client.delete("/admin/jobs/99999", headers=admin_auth)
    assert r.status_code == 404


def test_admin_endpoints_require_admin(client, regular_auth):
    """Regular users should get 403 on admin endpoints."""
    assert client.get("/admin/jobs/stats", headers=regular_auth).status_code == 403
    assert client.get("/admin/jobs", headers=regular_auth).status_code == 403
    assert client.post("/admin/jobs/process", headers=regular_auth).status_code == 403


def test_admin_endpoints_require_auth(client):
    """Unauthenticated requests should get 401."""
    assert client.get("/admin/jobs/stats").status_code == 401


def test_admin_retry_dead_letter_via_api(client, admin_auth, app_ctx):
    """Full flow: create dead-letter job, retry via API."""
    @register_handler("api_retry_test")
    def handle_api_retry(payload):
        raise ValueError("fail for test")

    job = enqueue("api_retry_test", max_retries=1)
    execute_job(job)
    assert job.status == JobStatus.DEAD_LETTER

    r = client.post(f"/admin/jobs/{job.id}/retry", headers=admin_auth)
    assert r.status_code == 200
    assert r.get_json()["status"] == "retried"

    _job_handlers.pop("api_retry_test", None)


def test_admin_retry_non_dead_letter_fails(client, admin_auth, app_ctx):
    @register_handler("pending_retry")
    def handle_pending(payload):
        return {"ok": True}

    job = enqueue("pending_retry")
    r = client.post(f"/admin/jobs/{job.id}/retry", headers=admin_auth)
    assert r.status_code == 400

    _job_handlers.pop("pending_retry", None)
