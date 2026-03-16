"""Tests for background job retry & monitoring system."""

import json
from datetime import datetime, timedelta

import pytest


# ── Helper ────────────────────────────────────────────────────────────────────


def _register_user_as_admin(app_fixture):
    """Promote the test user to ADMIN within the app context."""
    with app_fixture.app_context():
        from app.extensions import db
        from app.models import User

        user = User.query.filter_by(email="test@example.com").first()
        if user:
            user.role = "ADMIN"
            db.session.commit()


# ── Job service unit tests ────────────────────────────────────────────────────


def test_enqueue_creates_pending_job(app_fixture):
    with app_fixture.app_context():
        from app.services.jobs import enqueue
        from app.models import BackgroundJob

        job = enqueue("noop_test", {"key": "value"})
        assert job.id is not None
        assert job.status == "PENDING"
        assert job.attempts == 0
        assert job.job_type == "noop_test"
        loaded = BackgroundJob.query.get(job.id)
        assert loaded is not None


def test_successful_job_execution(app_fixture):
    with app_fixture.app_context():
        from app.services.jobs import enqueue, _run_single_job, register_job_handler

        results = []

        @register_job_handler("test_succeed")
        def _handler(payload):
            results.append(payload.get("value"))

        job = enqueue("test_succeed", {"value": 42})
        _run_single_job(job)

        assert job.status == "SUCCEEDED"
        assert job.finished_at is not None
        assert results == [42]


def test_failed_job_is_retried(app_fixture):
    with app_fixture.app_context():
        from app.services.jobs import enqueue, _run_single_job, register_job_handler

        call_count = [0]

        @register_job_handler("test_fail_once")
        def _handler(payload):
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("transient failure")

        job = enqueue("test_fail_once", {})
        _run_single_job(job)  # fails, status stays PENDING
        assert job.status == "PENDING"
        assert job.attempts == 1
        assert job.last_error == "transient failure"
        assert job.next_run_at > datetime.utcnow()

        # Reset next_run_at to now so second run fires
        job.next_run_at = datetime.utcnow()
        from app.extensions import db
        db.session.commit()

        _run_single_job(job)  # succeeds
        assert job.status == "SUCCEEDED"


def test_job_marked_dead_after_max_attempts(app_fixture):
    with app_fixture.app_context():
        from app.services.jobs import enqueue, _run_single_job, register_job_handler, MAX_ATTEMPTS

        @register_job_handler("test_always_fail")
        def _handler(payload):
            raise RuntimeError("always fails")

        job = enqueue("test_always_fail", {})
        for _ in range(MAX_ATTEMPTS):
            job.status = "PENDING"
            job.next_run_at = datetime.utcnow()
            from app.extensions import db
            db.session.commit()
            _run_single_job(job)

        assert job.status == "DEAD"
        assert job.attempts == MAX_ATTEMPTS


def test_unknown_job_type_marked_dead(app_fixture):
    with app_fixture.app_context():
        from app.services.jobs import enqueue, _run_single_job

        job = enqueue("this_handler_doesnt_exist", {})
        _run_single_job(job)
        assert job.status == "DEAD"
        assert "No handler registered" in (job.last_error or "")


# ── Monitoring API tests ──────────────────────────────────────────────────────


def test_job_stats_requires_admin(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 403


def test_job_list_requires_admin(client, auth_header):
    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 403


def test_job_stats_as_admin(client, auth_header, app_fixture):
    _register_user_as_admin(app_fixture)
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "pending" in data
    assert "succeeded" in data
    assert "dead" in data
    assert "total" in data


def test_job_list_as_admin(client, auth_header, app_fixture):
    _register_user_as_admin(app_fixture)

    # Enqueue a job first
    r = client.post(
        "/jobs/enqueue",
        json={"job_type": "noop_x", "payload": {"x": 1}},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 200
    jobs = r.get_json()
    assert isinstance(jobs, list)
    assert any(j["job_type"] == "noop_x" for j in jobs)


def test_retry_dead_job(client, auth_header, app_fixture):
    _register_user_as_admin(app_fixture)

    # Enqueue and set it to DEAD manually
    r = client.post(
        "/jobs/enqueue",
        json={"job_type": "noop_dead", "payload": {}},
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    with app_fixture.app_context():
        from app.extensions import db
        from app.models import BackgroundJob

        job = BackgroundJob.query.get(job_id)
        job.status = "DEAD"
        db.session.commit()

    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["status"] == "PENDING"
    assert r.get_json()["attempts"] == 0


def test_retry_non_dead_job_fails(client, auth_header, app_fixture):
    _register_user_as_admin(app_fixture)

    r = client.post(
        "/jobs/enqueue",
        json={"job_type": "pending_job", "payload": {}},
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 400


def test_enqueue_requires_job_type(client, auth_header, app_fixture):
    _register_user_as_admin(app_fixture)
    r = client.post("/jobs/enqueue", json={"payload": {}}, headers=auth_header)
    assert r.status_code == 400


def test_jobs_endpoint_requires_auth(client):
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs/stats").status_code == 401
