"""Tests for background job retry & monitoring system."""
from datetime import datetime, timedelta
from unittest.mock import patch

from app.extensions import db
from app.models import BackgroundJob, JobStatus
from app.services.job_runner import BackgroundJobRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_job(app_fixture, job_type="test_job", payload=None, status=JobStatus.PENDING.value, max_retries=5):
    """Helper to insert a job directly into the DB."""
    with app_fixture.app_context():
        job = BackgroundJob(
            job_type=job_type,
            payload=payload,
            status=status,
            max_retries=max_retries,
        )
        db.session.add(job)
        db.session.commit()
        return job.id


def _get_auth(client, auth_header):
    return auth_header


# ---------------------------------------------------------------------------
# Job Runner Unit Tests
# ---------------------------------------------------------------------------

def test_enqueue_and_execute_job(app_fixture):
    """A registered handler should be called and job marked completed."""
    runner = BackgroundJobRunner()
    called_with = []

    def handler(payload):
        called_with.append(payload)

    runner.register("my_job", handler)

    with app_fixture.app_context():
        job = runner.enqueue_job("my_job", {"key": "value"})
        assert job.status == JobStatus.PENDING.value
        assert job.id is not None

        result = runner.execute_job(job.id)
        assert result.status == JobStatus.COMPLETED.value
        assert result.attempts == 1
        assert result.completed_at is not None
        assert called_with == [{"key": "value"}]


def test_retry_on_failure(app_fixture):
    """A failing job should be marked FAILED with next_retry_at set."""
    runner = BackgroundJobRunner()
    call_count = 0

    def flaky_handler(payload):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("boom")

    runner.register("flaky", flaky_handler)

    with app_fixture.app_context():
        job = runner.enqueue_job("flaky", max_retries=3)
        result = runner.execute_job(job.id)

        assert result.status == JobStatus.FAILED.value
        assert result.attempts == 1
        assert result.last_error is not None
        assert "boom" in result.last_error
        assert result.next_retry_at is not None
        assert result.next_retry_at > datetime.utcnow()


def test_dead_letter_after_max_retries(app_fixture):
    """After max_retries failures the job should be dead-lettered."""
    runner = BackgroundJobRunner()

    def always_fail(payload):
        raise ValueError("always fails")

    runner.register("fail", always_fail)

    with app_fixture.app_context():
        job = runner.enqueue_job("fail", max_retries=2)
        # First attempt
        runner.execute_job(job.id)
        # Second attempt
        result = runner.execute_job(job.id)
        assert result.status == JobStatus.DEAD_LETTER.value
        assert result.attempts == 2
        assert result.completed_at is not None


def test_no_handler_dead_letters(app_fixture):
    """A job with no registered handler should be dead-lettered immediately."""
    runner = BackgroundJobRunner()

    with app_fixture.app_context():
        job = runner.enqueue_job("unknown_type")
        result = runner.execute_job(job.id)
        assert result.status == JobStatus.DEAD_LETTER.value
        assert "No handler" in result.last_error


def test_process_pending(app_fixture):
    """process_pending should pick up pending jobs."""
    runner = BackgroundJobRunner()
    processed = []

    def handler(payload):
        processed.append(payload)

    runner.register("batch", handler)

    with app_fixture.app_context():
        runner.enqueue_job("batch", {"a": 1})
        runner.enqueue_job("batch", {"a": 2})
        results = runner.process_pending()
        assert len(results) == 2
        assert all(r.status == JobStatus.COMPLETED.value for r in results)
        assert len(processed) == 2


def test_process_pending_includes_retry_ready(app_fixture):
    """process_pending should also pick up failed jobs whose next_retry_at has passed."""
    runner = BackgroundJobRunner()
    call_count = 0

    def handler(payload):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("first try fails")

    runner.register("retry_test", handler)

    with app_fixture.app_context():
        job = runner.enqueue_job("retry_test", max_retries=3)
        # First attempt - fails
        runner.execute_job(job.id)
        assert job.status == JobStatus.FAILED.value

        # Simulate retry time having passed
        job.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

        # process_pending should pick it up
        results = runner.process_pending()
        assert len(results) == 1
        assert results[0].status == JobStatus.COMPLETED.value


def test_backoff_delay():
    """Exponential backoff should be min(2^attempt * 30, 3600)."""
    assert BackgroundJobRunner._backoff_delay(1) == 60   # 2^1 * 30
    assert BackgroundJobRunner._backoff_delay(2) == 120  # 2^2 * 30
    assert BackgroundJobRunner._backoff_delay(3) == 240  # 2^3 * 30
    assert BackgroundJobRunner._backoff_delay(4) == 480  # 2^4 * 30
    assert BackgroundJobRunner._backoff_delay(5) == 960  # 2^5 * 30
    assert BackgroundJobRunner._backoff_delay(6) == 1920 # 2^6 * 30
    assert BackgroundJobRunner._backoff_delay(7) == 3600 # 2^7 * 30 = 3840, capped at 3600
    assert BackgroundJobRunner._backoff_delay(8) == 3600


def test_get_job_stats(app_fixture):
    """get_job_stats should return counts by status."""
    runner = BackgroundJobRunner()

    def ok_handler(payload):
        pass

    def bad_handler(payload):
        raise RuntimeError("fail")

    runner.register("ok", ok_handler)
    runner.register("bad", bad_handler)

    with app_fixture.app_context():
        runner.enqueue_job("ok")
        runner.enqueue_job("bad", max_retries=1)
        runner.enqueue_job("bad", max_retries=1)
        runner.process_pending()  # ok completes, bad x2 fail then dead_letter

        stats = runner.get_job_stats()
        assert stats["counts"][JobStatus.COMPLETED.value] == 1
        assert stats["counts"][JobStatus.DEAD_LETTER.value] == 2
        assert len(stats["recent_failures"]) == 2


def test_skip_non_executable_job(app_fixture):
    """execute_job on a completed job should return it unchanged."""
    runner = BackgroundJobRunner()

    def handler(payload):
        pass

    runner.register("noop", handler)

    with app_fixture.app_context():
        job = runner.enqueue_job("noop")
        runner.execute_job(job.id)
        assert job.status == JobStatus.COMPLETED.value

        # Try to execute again
        result = runner.execute_job(job.id)
        assert result.status == JobStatus.COMPLETED.value  # unchanged


# ---------------------------------------------------------------------------
# API Route Tests
# ---------------------------------------------------------------------------

def test_job_stats_endpoint(client, auth_header):
    """GET /jobs/stats should return stats with proper auth."""
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "counts" in data
    assert "recent_failures" in data


def test_job_stats_requires_auth(client):
    """GET /jobs/stats without auth should return 401."""
    r = client.get("/jobs/stats")
    assert r.status_code == 401


def test_list_jobs_empty(client, auth_header):
    """GET /jobs should return empty list when no jobs exist."""
    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["jobs"] == []
    assert data["total"] == 0


def test_list_jobs_with_data(client, auth_header, app_fixture):
    """GET /jobs should list jobs after creation."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        runner.enqueue_job("test", {"x": 1})
        runner.enqueue_job("test", {"x": 2})

    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    assert len(data["jobs"]) == 2


def test_list_jobs_filter_by_status(client, auth_header, app_fixture):
    """GET /jobs?status=pending should filter results."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        runner.enqueue_job("test")
        job2 = runner.enqueue_job("test")
        runner.execute_job(job2.id)  # completes

    r = client.get("/jobs?status=pending", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert all(j["status"] == "pending" for j in data["jobs"])


def test_list_jobs_filter_by_job_type(client, auth_header, app_fixture):
    """GET /jobs?job_type=email should filter results."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("email", lambda p: None)
        runner.register("sms", lambda p: None)
        runner.enqueue_job("email")
        runner.enqueue_job("sms")

    r = client.get("/jobs?job_type=email", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["jobs"][0]["job_type"] == "email"


def test_list_jobs_pagination(client, auth_header, app_fixture):
    """GET /jobs?page=1&page_size=1 should paginate."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        runner.enqueue_job("test")
        runner.enqueue_job("test")
        runner.enqueue_job("test")

    r = client.get("/jobs?page=1&page_size=1", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["jobs"]) == 1
    assert data["total"] == 3


def test_get_single_job(client, auth_header, app_fixture):
    """GET /jobs/<id> should return a single job."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        job = runner.enqueue_job("test", {"key": "val"})
        job_id = job.id

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == job_id
    assert data["job_type"] == "test"
    assert data["payload"] == {"key": "val"}


def test_get_job_not_found(client, auth_header):
    """GET /jobs/9999 should return 404."""
    r = client.get("/jobs/9999", headers=auth_header)
    assert r.status_code == 404


def test_retry_dead_letter_job(client, auth_header, app_fixture):
    """POST /jobs/<id>/retry should retry a dead_letter job."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        call_count = 0

        def handler(payload):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("fail first tries")

        runner.register("recover", handler)
        job = runner.enqueue_job("recover", max_retries=2)
        # Fail twice -> dead letter
        runner.execute_job(job.id)
        runner.execute_job(job.id)
        assert job.status == JobStatus.DEAD_LETTER.value
        job_id = job.id

    # Manual retry - third try succeeds
    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "completed"


def test_retry_non_dead_letter_rejected(client, auth_header, app_fixture):
    """POST /jobs/<id>/retry on a pending job should return 400."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        job = runner.enqueue_job("test")
        job_id = job.id

    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 400


def test_cancel_pending_job(client, auth_header, app_fixture):
    """POST /jobs/<id>/cancel should cancel a pending job."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        job = runner.enqueue_job("test")
        job_id = job.id

    r = client.post(f"/jobs/{job_id}/cancel", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "cancelled"


def test_cancel_non_pending_rejected(client, auth_header, app_fixture):
    """POST /jobs/<id>/cancel on a completed job should return 400."""
    with app_fixture.app_context():
        runner = BackgroundJobRunner()
        runner.register("test", lambda p: None)
        job = runner.enqueue_job("test")
        runner.execute_job(job.id)
        job_id = job.id

    r = client.post(f"/jobs/{job_id}/cancel", headers=auth_header)
    assert r.status_code == 400


def test_cancel_not_found(client, auth_header):
    """POST /jobs/9999/cancel should return 404."""
    r = client.post("/jobs/9999/cancel", headers=auth_header)
    assert r.status_code == 404


def test_retry_not_found(client, auth_header):
    """POST /jobs/9999/retry should return 404."""
    r = client.post("/jobs/9999/retry", headers=auth_header)
    assert r.status_code == 404


def test_invalid_pagination(client, auth_header):
    """GET /jobs?page=abc should return 400."""
    r = client.get("/jobs?page=abc", headers=auth_header)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

def test_background_job_model_defaults(app_fixture):
    """BackgroundJob model should have correct defaults."""
    with app_fixture.app_context():
        job = BackgroundJob(job_type="test")
        db.session.add(job)
        db.session.commit()

        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.attempts == 0
        assert job.max_retries == 5
        assert job.created_at is not None
        assert job.payload is None
        assert job.last_error is None
        assert job.next_retry_at is not None is False or job.next_retry_at is None
        assert job.started_at is None
        assert job.completed_at is None


def test_background_job_with_payload(app_fixture):
    """BackgroundJob should store JSON payloads."""
    with app_fixture.app_context():
        payload = {"user_id": 1, "action": "send_email", "data": [1, 2, 3]}
        job = BackgroundJob(job_type="email", payload=payload)
        db.session.add(job)
        db.session.commit()

        loaded = db.session.get(BackgroundJob, job.id)
        assert loaded.payload == payload
