"""
Tests for resilient background job retry & monitoring.

Covers:
- Job creation and execution lifecycle
- Exponential backoff calculation
- Circuit breaker state transitions
- Retry exhaustion (dead-letter)
- Manual retry of failed jobs
- Job monitoring API endpoints
- Statistics and health check endpoints
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models import JobExecution, JobStatus, Reminder
from app.services.job_scheduler import (
    CircuitBreaker,
    calculate_backoff,
    create_job,
    execute_job,
    get_job_stats,
    manually_retry_job,
    retry_pending_jobs,
    dispatch_reminder_with_retry,
    email_breaker,
    whatsapp_breaker,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Override conftest auth_header to mock Redis for local testing
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_header(client):
    """Auth header fixture with Redis mocked out."""
    mock_redis = MagicMock()
    with patch("app.routes.auth.redis_client", mock_redis):
        email = "test@example.com"
        password = "password123"
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (200, 201, 409)
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        access = r.get_json()["access_token"]
        return {"Authorization": f"Bearer {access}"}


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------


def test_backoff_increases_exponentially():
    b0 = calculate_backoff(0, base_seconds=300)
    b1 = calculate_backoff(1, base_seconds=300)
    b2 = calculate_backoff(2, base_seconds=300)

    # Retry 0: ~300s, Retry 1: ~900s, Retry 2: ~2700s (with ±10% jitter)
    assert 270 <= b0 <= 330
    assert 810 <= b1 <= 990
    assert 2430 <= b2 <= 2970


def test_backoff_with_custom_base():
    b0 = calculate_backoff(0, base_seconds=60)
    assert 54 <= b0 <= 66  # 60 ± 10%


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_stays_closed_under_threshold():
    cb = CircuitBreaker("test", failure_threshold=3, reset_timeout_seconds=10)
    assert cb.can_execute() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_opens_at_threshold():
    cb = CircuitBreaker("test", failure_threshold=3, reset_timeout_seconds=10)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.can_execute() is False


def test_circuit_breaker_half_open_after_timeout():
    cb = CircuitBreaker("test", failure_threshold=2, reset_timeout_seconds=1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    # Simulate time passing
    cb.last_failure_time = datetime.utcnow() - timedelta(seconds=2)
    assert cb.can_execute() is True
    assert cb.state == CircuitBreaker.HALF_OPEN


def test_circuit_breaker_closes_on_success_after_half_open():
    cb = CircuitBreaker("test", failure_threshold=2, reset_timeout_seconds=1)
    cb.record_failure()
    cb.record_failure()
    cb.last_failure_time = datetime.utcnow() - timedelta(seconds=2)
    cb.can_execute()  # transitions to HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_status_dict():
    cb = CircuitBreaker("test_svc", failure_threshold=5, reset_timeout_seconds=60)
    status = cb.get_status()
    assert status["name"] == "test_svc"
    assert status["state"] == "CLOSED"
    assert status["failure_threshold"] == 5


# ---------------------------------------------------------------------------
# Job creation and execution
# ---------------------------------------------------------------------------


def test_create_job(app_fixture):
    with app_fixture.app_context():
        job = create_job("test_type", payload={"key": "value"}, max_retries=5)
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.job_type == "test_type"
        assert json.loads(job.payload) == {"key": "value"}
        assert job.max_retries == 5
        assert job.retry_count == 0


def test_execute_job_success(app_fixture):
    with app_fixture.app_context():
        job = create_job("test_type", payload={"channel": "email"})

        def handler(payload):
            return "done"

        # Reset email breaker state
        email_breaker.state = CircuitBreaker.CLOSED
        email_breaker.failure_count = 0

        success = execute_job(job, handler)
        assert success is True
        assert job.status == JobStatus.COMPLETED.value
        assert job.completed_at is not None
        result = json.loads(job.result)
        assert result["success"] is True


def test_execute_job_failure_schedules_retry(app_fixture):
    with app_fixture.app_context():
        job = create_job("test_type", payload={"channel": "email"}, max_retries=3)

        def handler(payload):
            raise RuntimeError("Service unavailable")

        email_breaker.state = CircuitBreaker.CLOSED
        email_breaker.failure_count = 0

        success = execute_job(job, handler)
        assert success is False
        assert job.status == JobStatus.RETRYING.value
        assert job.retry_count == 1
        assert job.next_retry_at is not None
        assert "Service unavailable" in job.last_error


def test_execute_job_exhausts_retries(app_fixture):
    with app_fixture.app_context():
        job = create_job("test_type", payload={"channel": "email"}, max_retries=1)

        def handler(payload):
            raise RuntimeError("Permanent failure")

        email_breaker.state = CircuitBreaker.CLOSED
        email_breaker.failure_count = 0

        success = execute_job(job, handler)
        assert success is False
        assert job.status == JobStatus.DEAD.value
        assert job.retry_count == 1
        result = json.loads(job.result)
        assert result["success"] is False
        assert "Exhausted" in result["detail"]


def test_execute_job_circuit_breaker_blocks(app_fixture):
    with app_fixture.app_context():
        job = create_job("test_type", payload={"channel": "email"}, max_retries=3)

        # Force breaker open
        email_breaker.state = CircuitBreaker.OPEN
        email_breaker.last_failure_time = datetime.utcnow()
        email_breaker.failure_count = 10

        def handler(payload):
            return "should not run"

        success = execute_job(job, handler)
        assert success is False
        assert job.status == JobStatus.RETRYING.value
        assert "Circuit breaker" in job.last_error

        # Reset
        email_breaker.state = CircuitBreaker.CLOSED
        email_breaker.failure_count = 0


# ---------------------------------------------------------------------------
# Retry processing
# ---------------------------------------------------------------------------


def test_retry_pending_jobs(app_fixture):
    with app_fixture.app_context():
        from app.services.job_scheduler import register_job_handler

        results = []

        def test_handler(payload):
            results.append(payload)
            return "ok"

        register_job_handler("retry_test", test_handler)

        job = create_job("retry_test", payload={"data": 42}, max_retries=3)
        job.status = JobStatus.RETRYING.value
        job.retry_count = 1
        job.next_retry_at = datetime.utcnow() - timedelta(seconds=10)
        db.session.commit()

        email_breaker.state = CircuitBreaker.CLOSED
        email_breaker.failure_count = 0

        summary = retry_pending_jobs()
        assert summary["processed"] == 1
        assert summary["succeeded"] == 1
        assert len(results) == 1


def test_retry_pending_jobs_skips_future(app_fixture):
    with app_fixture.app_context():
        job = create_job("retry_test", payload={}, max_retries=3)
        job.status = JobStatus.RETRYING.value
        job.retry_count = 1
        job.next_retry_at = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()

        summary = retry_pending_jobs()
        assert summary["processed"] == 0


# ---------------------------------------------------------------------------
# Manual retry
# ---------------------------------------------------------------------------


def test_manual_retry_resets_dead_job(app_fixture):
    with app_fixture.app_context():
        from app.services.job_scheduler import register_job_handler

        def test_handler(payload):
            return "recovered"

        register_job_handler("manual_retry_test", test_handler)

        job = create_job("manual_retry_test", payload={"channel": "email"})
        job.status = JobStatus.DEAD.value
        job.retry_count = 3
        job.last_error = "Some failure"
        db.session.commit()

        email_breaker.state = CircuitBreaker.CLOSED
        email_breaker.failure_count = 0

        retried = manually_retry_job(job.id)
        assert retried is not None
        assert retried.status == JobStatus.COMPLETED.value
        assert retried.retry_count == 0


def test_manual_retry_rejects_running_job(app_fixture):
    with app_fixture.app_context():
        job = create_job("test_type", payload={})
        job.status = JobStatus.RUNNING.value
        db.session.commit()

        result = manually_retry_job(job.id)
        assert result is None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_job_stats(app_fixture):
    with app_fixture.app_context():
        # Create a mix of jobs
        j1 = create_job("type_a", payload={})
        j1.status = JobStatus.COMPLETED.value
        j1.started_at = datetime.utcnow() - timedelta(seconds=2)
        j1.completed_at = datetime.utcnow()

        j2 = create_job("type_a", payload={})
        j2.status = JobStatus.DEAD.value

        j3 = create_job("type_b", payload={})
        j3.status = JobStatus.RETRYING.value
        db.session.commit()

        stats = get_job_stats()
        assert stats["total_jobs"] == 3
        assert stats["by_status"][JobStatus.COMPLETED.value] == 1
        assert stats["by_status"][JobStatus.DEAD.value] == 1
        assert stats["success_rate_percent"] == 50.0
        assert stats["avg_duration_seconds"] is not None
        assert "email" in stats["circuit_breakers"]
        assert "whatsapp" in stats["circuit_breakers"]


# ---------------------------------------------------------------------------
# Reminder job integration
# ---------------------------------------------------------------------------


def test_dispatch_reminder_with_retry(app_fixture):
    with app_fixture.app_context():
        from app.models import User
        from werkzeug.security import generate_password_hash

        user = User(
            email="jobtest@example.com",
            password_hash=generate_password_hash("pass"),
        )
        db.session.add(user)
        db.session.commit()

        reminder = Reminder(
            user_id=user.id,
            message="Pay your bill!",
            send_at=datetime.utcnow(),
            channel="email",
        )
        db.session.add(reminder)
        db.session.commit()

        job = dispatch_reminder_with_retry(reminder, max_retries=2)
        assert job.job_type == "reminder_dispatch"
        assert job.max_retries == 2
        payload = json.loads(job.payload)
        assert payload["reminder_id"] == reminder.id
        assert payload["channel"] == "email"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_jobs_health_endpoint(client):
    r = client.get("/jobs/health")
    assert r.status_code == 200
    data = r.get_json()
    assert "healthy" in data
    assert "circuit_breakers" in data


def test_jobs_status_requires_auth(client):
    r = client.get("/jobs/status")
    assert r.status_code == 401


def test_jobs_status_returns_paginated_list(client, auth_header, app_fixture):
    with app_fixture.app_context():
        # Create some jobs for user 1
        for i in range(3):
            job = create_job("test_type", payload={"i": i}, user_id=1)
            job.status = JobStatus.COMPLETED.value
            db.session.commit()

    r = client.get("/jobs/status", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "jobs" in data
    assert "pagination" in data
    assert len(data["jobs"]) == 3
    assert data["pagination"]["total"] == 3


def test_jobs_status_filter_by_status(client, auth_header, app_fixture):
    with app_fixture.app_context():
        j1 = create_job("t", payload={}, user_id=1)
        j1.status = JobStatus.COMPLETED.value
        j2 = create_job("t", payload={}, user_id=1)
        j2.status = JobStatus.DEAD.value
        db.session.commit()

    r = client.get("/jobs/status?status=DEAD", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == "DEAD"


def test_jobs_stats_endpoint(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "total_jobs" in data
    assert "circuit_breakers" in data


def test_jobs_retry_endpoint(client, auth_header, app_fixture):
    with app_fixture.app_context():
        from app.services.job_scheduler import register_job_handler

        def test_handler(payload):
            return "recovered"

        register_job_handler("retry_api_test", test_handler)

        job = create_job("retry_api_test", payload={"channel": "email"}, user_id=1)
        job.status = JobStatus.DEAD.value
        job.retry_count = 3
        db.session.commit()
        job_id = job.id

    email_breaker.state = CircuitBreaker.CLOSED
    email_breaker.failure_count = 0

    r = client.post(f"/jobs/retry/{job_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == JobStatus.COMPLETED.value


def test_jobs_retry_rejects_non_failed(client, auth_header, app_fixture):
    with app_fixture.app_context():
        job = create_job("test", payload={}, user_id=1)
        job.status = JobStatus.COMPLETED.value
        db.session.commit()
        job_id = job.id

    r = client.post(f"/jobs/retry/{job_id}", headers=auth_header)
    assert r.status_code == 400


def test_jobs_retry_404_for_other_user(client, auth_header, app_fixture):
    with app_fixture.app_context():
        job = create_job("test", payload={}, user_id=999)
        job.status = JobStatus.DEAD.value
        db.session.commit()
        job_id = job.id

    r = client.post(f"/jobs/retry/{job_id}", headers=auth_header)
    assert r.status_code == 404


def test_jobs_process_retries_endpoint(client, auth_header):
    r = client.post("/jobs/process-retries", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "processed" in data
    assert "succeeded" in data
    assert "failed" in data


def test_get_single_job(client, auth_header, app_fixture):
    with app_fixture.app_context():
        job = create_job("detail_test", payload={"key": "val"}, user_id=1)
        db.session.commit()
        job_id = job.id

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["job_type"] == "detail_test"


def test_get_single_job_404(client, auth_header):
    r = client.get("/jobs/999999", headers=auth_header)
    assert r.status_code == 404


def test_job_to_dict(app_fixture):
    with app_fixture.app_context():
        job = create_job("dict_test", payload={"a": 1}, user_id=1, max_retries=5)
        d = job.to_dict()
        assert d["job_type"] == "dict_test"
        assert d["max_retries"] == 5
        assert d["status"] == "PENDING"
        assert d["created_at"] is not None
