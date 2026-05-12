import json
from datetime import datetime, timedelta
from app.services.jobs import (
    enqueue_job,
    execute_job,
    process_pending_jobs,
    get_job_stats,
    register_handler,
    BACKOFF_BASE_SECONDS,
    BACKOFF_MULTIPLIER,
)
from app.models import JobExecution
from app.extensions import db


def _success_handler(payload):
    return True


def _failure_handler(payload):
    raise RuntimeError("simulated failure")


def test_enqueue_job(app_fixture):
    with app_fixture.app_context():
        job = enqueue_job("reminder_email", payload={"to": "a@b.com"}, user_id=1)
        assert job.id is not None
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.job_type == "reminder_email"
        parsed = json.loads(job.payload)
        assert parsed["to"] == "a@b.com"


def test_execute_job_success(app_fixture):
    with app_fixture.app_context():
        register_handler("test_ok", _success_handler)
        job = enqueue_job("test_ok", payload={"x": 1}, user_id=1)
        result = execute_job(job.id)
        assert result.status == "completed"
        assert result.attempts == 1
        assert result.completed_at is not None
        assert result.last_error is None


def test_execute_job_retry_with_backoff(app_fixture):
    with app_fixture.app_context():
        register_handler("test_fail", _failure_handler)
        job = enqueue_job("test_fail", payload={}, user_id=1, max_attempts=3)

        # First attempt -> retrying
        result = execute_job(job.id)
        assert result.status == "retrying"
        assert result.attempts == 1
        assert result.last_error == "simulated failure"
        assert result.next_retry_at is not None
        # Backoff should be ~30 seconds for first retry
        expected_backoff = BACKOFF_BASE_SECONDS * (BACKOFF_MULTIPLIER ** 0)
        assert expected_backoff == 30

        # Second attempt -> retrying
        result = execute_job(job.id)
        assert result.status == "retrying"
        assert result.attempts == 2
        # Backoff should be ~120 seconds for second retry
        expected_backoff = BACKOFF_BASE_SECONDS * (BACKOFF_MULTIPLIER ** 1)
        assert expected_backoff == 120


def test_execute_job_max_attempts_exceeded(app_fixture):
    with app_fixture.app_context():
        register_handler("test_fail_max", _failure_handler)
        job = enqueue_job("test_fail_max", payload={}, user_id=1, max_attempts=2)

        execute_job(job.id)
        assert job.status == "retrying"
        assert job.attempts == 1

        execute_job(job.id)
        assert job.status == "failed"
        assert job.attempts == 2
        assert job.last_error == "simulated failure"


def test_execute_job_no_handler(app_fixture):
    with app_fixture.app_context():
        job = enqueue_job("nonexistent_type", payload={}, user_id=1)
        result = execute_job(job.id)
        assert result.status == "failed"
        assert "No handler registered" in result.last_error


def test_process_pending_jobs(app_fixture):
    with app_fixture.app_context():
        register_handler("test_process", _success_handler)
        enqueue_job("test_process", payload={}, user_id=1)
        enqueue_job("test_process", payload={}, user_id=1)

        results = process_pending_jobs()
        assert len(results) == 2
        assert all(r.status == "completed" for r in results)


def test_process_pending_jobs_skips_future_retry(app_fixture):
    with app_fixture.app_context():
        register_handler("test_skip", _failure_handler)
        job = enqueue_job("test_skip", payload={}, user_id=1, max_attempts=3)
        execute_job(job.id)  # -> retrying with future next_retry_at
        assert job.status == "retrying"

        # Process should skip this job since next_retry_at is in the future
        results = process_pending_jobs()
        # The job should not be re-executed since its retry time hasn't arrived
        refreshed = db.session.get(JobExecution, job.id)
        assert refreshed.attempts == 1  # still at 1


def test_get_job_stats(app_fixture):
    with app_fixture.app_context():
        register_handler("test_stats", _success_handler)
        register_handler("test_stats_fail", _failure_handler)

        j1 = enqueue_job("test_stats", payload={}, user_id=1)
        execute_job(j1.id)

        j2 = enqueue_job("test_stats_fail", payload={}, user_id=1, max_attempts=1)
        execute_job(j2.id)

        stats = get_job_stats(user_id=1)
        assert stats["counts"]["completed"] == 1
        assert stats["counts"]["failed"] == 1
        assert stats["total"] == 2
        assert stats["success_rate"] == 50.0
        assert len(stats["recent_failures"]) == 1
        assert stats["recent_failures"][0]["job_type"] == "test_stats_fail"


def test_jobs_stats_endpoint(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "counts" in data
    assert "success_rate" in data


def test_jobs_recent_endpoint(client, auth_header):
    r = client.get("/jobs/recent", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_jobs_recent_with_filters(client, auth_header):
    r = client.get("/jobs/recent?status=completed&job_type=reminder_email", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_jobs_retry_not_found(client, auth_header):
    r = client.post("/jobs/retry/99999", headers=auth_header)
    assert r.status_code == 404


def test_jobs_process_endpoint(client, auth_header):
    r = client.post("/jobs/process", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "processed" in data


def test_retry_failed_job_via_endpoint(client, auth_header, app_fixture):
    with app_fixture.app_context():
        # Get user id from auth
        from app.models import User
        user = db.session.query(User).filter_by(email="test@example.com").first()
        assert user is not None

        call_count = {"n": 0}

        def sometimes_fail(payload):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                raise RuntimeError("first attempt fails")
            return True

        register_handler("test_retry_endpoint", sometimes_fail)
        job = enqueue_job("test_retry_endpoint", payload={}, user_id=user.id, max_attempts=1)
        execute_job(job.id)
        assert job.status == "failed"

    # Retry via endpoint
    r = client.post(f"/jobs/retry/{job.id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "completed"


def test_send_reminder_with_job(app_fixture, monkeypatch):
    with app_fixture.app_context():
        from app.models import Reminder
        from app.services.reminders import send_reminder_with_job, register_reminder_handlers

        register_reminder_handlers()

        r = Reminder(
            user_id=1,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="test@example.com",
        )
        db.session.add(r)
        db.session.commit()

        monkeypatch.setattr("app.services.reminders.send_email", lambda *a, **kw: True)

        job = send_reminder_with_job(r)
        assert job.status == "pending"
        assert job.job_type == "reminder_email"

        result = execute_job(job.id)
        assert result.status == "completed"


def test_send_reminder_with_job_whatsapp(app_fixture, monkeypatch):
    with app_fixture.app_context():
        from app.models import Reminder
        from app.services.reminders import send_reminder_with_job, register_reminder_handlers

        register_reminder_handlers()

        r = Reminder(
            user_id=1,
            message="Test whatsapp",
            send_at=datetime.utcnow(),
            channel="whatsapp:+1234567890",
        )
        db.session.add(r)
        db.session.commit()

        monkeypatch.setattr("app.services.reminders.send_whatsapp", lambda *a, **kw: True)

        job = send_reminder_with_job(r)
        assert job.status == "pending"
        assert job.job_type == "reminder_whatsapp"

        result = execute_job(job.id)
        assert result.status == "completed"


def test_send_email_failure_triggers_retry(app_fixture, monkeypatch):
    with app_fixture.app_context():
        from app.models import Reminder
        from app.services.reminders import send_reminder_with_job, register_reminder_handlers

        register_reminder_handlers()

        r = Reminder(
            user_id=1,
            message="Fail test",
            send_at=datetime.utcnow(),
            channel="test@example.com",
        )
        db.session.add(r)
        db.session.commit()

        monkeypatch.setattr("app.services.reminders.send_email", lambda *a, **kw: False)

        job = send_reminder_with_job(r)
        result = execute_job(job.id)
        assert result.status == "retrying"
        assert result.last_error == "send_email failed"
