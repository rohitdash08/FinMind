"""Tests for the resilient background job manager."""

import pytest
from app.services.job_manager import (
    compute_backoff_delay,
    enqueue,
    run_job,
    retry_failed_job,
    process_pending_jobs,
    list_jobs,
    dead_letter_jobs,
    job_stats,
    get_job,
    register_job_type,
    JobStatus,
    DEFAULT_MAX_RETRIES,
)
from app.models import Job
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestComputeBackoffDelay:
    def test_zero_attempt_returns_base_delay_range(self):
        delay = compute_backoff_delay(0, base_delay=2.0, jitter=False)
        assert delay == 2.0

    def test_increases_exponentially(self):
        d0 = compute_backoff_delay(0, jitter=False)
        d1 = compute_backoff_delay(1, jitter=False)
        d2 = compute_backoff_delay(2, jitter=False)
        assert d1 == d0 * 2
        assert d2 == d0 * 4

    def test_caps_at_max_delay(self):
        delay = compute_backoff_delay(100, base_delay=2.0, max_delay=300.0, jitter=False)
        assert delay == 300.0

    def test_jitter_modifies_delay(self):
        no_jitter = compute_backoff_delay(2, jitter=False)
        with_jitter = compute_backoff_delay(2, jitter=True)
        # jitter should produce a different value (deterministic but scaled)
        assert with_jitter != no_jitter
        # but still in a reasonable range
        assert 0 < with_jitter <= no_jitter * 1.1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop_handler(payload: dict):
    """A job that always succeeds."""
    pass


def _failing_handler(payload: dict):
    """A job that always fails."""
    raise RuntimeError("boom")


def _conditional_handler(payload: dict):
    """Fails first N times based on payload."""
    fail_until = payload.get("fail_until", 0)
    attempt = payload.get("_attempt_tracker", [0])
    # We can't mutate payload safely in prod, but for test purposes this works
    if len(attempt) <= fail_until:
        attempt.append(0)
        raise RuntimeError(f"failing on call {len(attempt) - 1}")


# ---------------------------------------------------------------------------
# DB-backed service tests (require app context)
# ---------------------------------------------------------------------------


class TestEnqueue:
    def test_creates_pending_job(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            job = enqueue("test_noop", {"key": "value"})
            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.job_type == "test_noop"
            assert job.payload == {"key": "value"}
            assert job.attempt == 0
            assert job.max_retries == DEFAULT_MAX_RETRIES

    def test_custom_max_retries(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue("test_noop", max_retries=3)
            assert job.max_retries == 3

    def test_scheduled_at(self, app_fixture):
        with app_fixture.app_context():
            future = datetime.utcnow() + timedelta(hours=1)
            job = enqueue("test_noop", scheduled_at=future)
            assert job.scheduled_at >= future - timedelta(seconds=1)


class TestRunJob:
    def test_success(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            job = enqueue("test_noop")
            result = run_job(job.id)
            assert result.status == JobStatus.SUCCESS.value
            assert result.attempt == 1
            assert result.completed_at is not None
            assert result.error_message is None

    def test_failure_increments_attempt(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_fail", _failing_handler)
            job = enqueue("test_fail", max_retries=3)
            result = run_job(job.id)
            assert result.status == JobStatus.FAILED.value
            assert result.attempt == 1
            assert "boom" in result.error_message
            assert result.next_retry_at is not None

    def test_dead_letter_after_max_retries(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_fail", _failing_handler)
            job = enqueue("test_fail", max_retries=1)
            # First attempt should dead-letter (attempt 1 >= max_retries 1)
            result = run_job(job.id)
            assert result.status == JobStatus.DEAD.value
            assert result.attempt == 1

    def test_unknown_job_type_dead_letters(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue("nonexistent_type")
            result = run_job(job.id)
            assert result.status == JobStatus.DEAD.value
            assert "Unknown job type" in result.error_message

    def test_skips_non_pending_job(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            job = enqueue("test_noop")
            run_job(job.id)  # SUCCESS
            result = run_job(job.id)  # should skip
            assert result.status == JobStatus.SUCCESS.value

    def test_not_found_raises(self, app_fixture):
        with app_fixture.app_context():
            with pytest.raises(ValueError, match="not found"):
                run_job(99999)


class TestRetryFailedJob:
    def test_retry_resets_failed_job(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_fail", _failing_handler)
            job = enqueue("test_fail", max_retries=3)
            run_job(job.id)  # FAILED
            assert get_job(job.id).status == JobStatus.FAILED.value

            retried = retry_failed_job(job.id)
            assert retried.status == JobStatus.PENDING.value
            assert retried.attempt == 0

    def test_retry_resets_dead_job(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_fail", _failing_handler)
            job = enqueue("test_fail", max_retries=1)
            run_job(job.id)  # DEAD
            assert get_job(job.id).status == JobStatus.DEAD.value

            retried = retry_failed_job(job.id)
            assert retried.status == JobStatus.PENDING.value

    def test_retry_pending_raises(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue("test_noop")
            with pytest.raises(ValueError, match="cannot retry"):
                retry_failed_job(job.id)

    def test_retry_not_found_raises(self, app_fixture):
        with app_fixture.app_context():
            with pytest.raises(ValueError, match="not found"):
                retry_failed_job(99999)


class TestProcessPendingJobs:
    def test_processes_due_jobs(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            enqueue("test_noop")
            enqueue("test_noop")
            results = process_pending_jobs(limit=10)
            assert len(results) == 2
            assert all(j.status == JobStatus.SUCCESS.value for j in results)

    def test_skips_future_jobs(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            enqueue("test_noop", scheduled_at=datetime.utcnow() + timedelta(hours=1))
            results = process_pending_jobs()
            assert len(results) == 0

    def test_respects_next_retry_at(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_fail", _failing_handler)
            job = enqueue("test_fail", max_retries=3)
            run_job(job.id)  # FAILED, next_retry_at in the future
            # Should not pick it up immediately
            results = process_pending_jobs()
            assert len(results) == 0


class TestListAndStats:
    def test_list_all(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            enqueue("test_noop")
            enqueue("test_noop")
            items, total = list_jobs()
            assert total == 2
            assert len(items) == 2

    def test_list_filtered_by_status(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            register_job_type("test_fail", _failing_handler)
            enqueue("test_noop")
            j2 = enqueue("test_fail", max_retries=3)
            run_job(j2.id)

            items, total = list_jobs(status=JobStatus.FAILED.value)
            assert total == 1
            assert items[0].status == JobStatus.FAILED.value

    def test_list_filtered_by_type(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("alpha", _noop_handler)
            register_job_type("beta", _noop_handler)
            enqueue("alpha")
            enqueue("beta")
            items, total = list_jobs(job_type="alpha")
            assert total == 1

    def test_pagination(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            for _ in range(5):
                enqueue("test_noop")
            items, total = list_jobs(page=1, per_page=2)
            assert total == 5
            assert len(items) == 2
            items2, _ = list_jobs(page=2, per_page=2)
            assert len(items2) == 2

    def test_dead_letter_queue(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_fail", _failing_handler)
            job = enqueue("test_fail", max_retries=1)
            run_job(job.id)
            items, total = dead_letter_jobs()
            assert total == 1
            assert items[0].status == JobStatus.DEAD.value

    def test_stats(self, app_fixture):
        with app_fixture.app_context():
            register_job_type("test_noop", _noop_handler)
            register_job_type("test_fail", _failing_handler)
            j1 = enqueue("test_noop")
            j2 = enqueue("test_fail", max_retries=3)
            run_job(j1.id)
            run_job(j2.id)
            s = job_stats()
            assert s.get(JobStatus.SUCCESS.value, 0) == 1
            assert s.get(JobStatus.FAILED.value, 0) == 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestJobsAPI:
    def test_list_jobs_endpoint(self, client, auth_header):
        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "jobs" in data
        assert "total" in data

    def test_create_job_endpoint(self, client, auth_header):
        register_job_type("api_test", _noop_handler)
        r = client.post(
            "/jobs",
            json={"job_type": "api_test", "payload": {"x": 1}},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["job_type"] == "api_test"
        assert data["status"] == "PENDING"

    def test_create_job_missing_type(self, client, auth_header):
        r = client.post("/jobs", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_get_job_endpoint(self, client, auth_header):
        register_job_type("api_test", _noop_handler)
        r = client.post(
            "/jobs",
            json={"job_type": "api_test"},
            headers=auth_header,
        )
        job_id = r.get_json()["id"]
        r = client.get(f"/jobs/{job_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == job_id

    def test_get_job_not_found(self, client, auth_header):
        r = client.get("/jobs/99999", headers=auth_header)
        assert r.status_code == 404

    def test_retry_endpoint(self, client, auth_header):
        register_job_type("api_fail", _failing_handler)
        r = client.post(
            "/jobs",
            json={"job_type": "api_fail", "max_retries": 3},
            headers=auth_header,
        )
        job_id = r.get_json()["id"]
        # Process it so it fails
        client.post("/jobs/process", headers=auth_header)

        r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "PENDING"

    def test_retry_pending_returns_400(self, client, auth_header):
        register_job_type("api_test", _noop_handler)
        r = client.post(
            "/jobs",
            json={"job_type": "api_test"},
            headers=auth_header,
        )
        job_id = r.get_json()["id"]
        r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
        assert r.status_code == 400

    def test_process_endpoint(self, client, auth_header):
        register_job_type("api_test", _noop_handler)
        client.post(
            "/jobs",
            json={"job_type": "api_test"},
            headers=auth_header,
        )
        r = client.post("/jobs/process", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["processed"] == 1

    def test_stats_endpoint(self, client, auth_header):
        r = client.get("/jobs/stats", headers=auth_header)
        assert r.status_code == 200
        assert "stats" in r.get_json()

    def test_dead_letter_endpoint(self, client, auth_header):
        r = client.get("/jobs/dead-letter", headers=auth_header)
        assert r.status_code == 200
        assert "jobs" in r.get_json()

    def test_types_endpoint(self, client, auth_header):
        r = client.get("/jobs/types", headers=auth_header)
        assert r.status_code == 200
        assert "types" in r.get_json()

    def test_invalid_status_filter(self, client, auth_header):
        r = client.get("/jobs?status=INVALID", headers=auth_header)
        assert r.status_code == 400

    def test_create_job_invalid_max_retries(self, client, auth_header):
        r = client.post(
            "/jobs",
            json={"job_type": "x", "max_retries": -1},
            headers=auth_header,
        )
        assert r.status_code == 400
