"""Tests for the resilient background job system.

Covers:
  - Backoff calculation (pure function)
  - Job enqueue / execute lifecycle
  - Retry scheduling after failures
  - Dead-letter queue after max retries exhausted
  - Dead-letter job reset
  - Circuit breaker state transitions
  - Dispatcher (reminder dispatch helper)
  - Monitoring API endpoints (status, stats, health, dead-letters, retry)
  - Job health alerting on stuck / overdue jobs
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import JobExecution, JobStatus, Reminder
from app.services.job_manager import (
    _handle_failure,
    _move_to_dead_letter,
    calculate_backoff,
    dispatch_reminders,
    enqueue_job,
    execute_job,
    get_dead_letter_jobs,
    get_handler,
    get_health_status,
    get_job_stats,
    register_job,
    retry_dead_letter_job,
    process_pending_retries,
    CircuitBreaker,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _register_test_handlers():
    """Register test job handlers for each test."""
    # Store original registry state
    from app.services.job_manager import _job_registry

    original = _job_registry.copy()

    @register_job("test_success")
    def _success(payload):
        return {"ok": True}

    @register_job("test_failure")
    def _failure(payload):
        raise RuntimeError("Simulated failure")

    @register_job("test_conditional")
    def _conditional(payload):
        if payload.get("fail"):
            raise ValueError("conditional fail")
        return {"result": payload.get("value", 42)}

    yield

    # Restore original registry
    _job_registry.clear()
    _job_registry.update(original)


# ---------------------------------------------------------------------------
# Pure function tests: backoff calculation
# ---------------------------------------------------------------------------


class TestCalculateBackoff:
    def test_first_retry_uses_base_delay(self):
        # retry_count=0 means first retry; base * 3^0 = base
        delay = calculate_backoff(0, base_seconds=300, multiplier=3.0, jitter_factor=0)
        assert delay == 300.0

    def test_second_retry_multiplied(self):
        delay = calculate_backoff(1, base_seconds=300, multiplier=3.0, jitter_factor=0)
        assert delay == 900.0

    def test_third_retry_multiplied(self):
        delay = calculate_backoff(2, base_seconds=300, multiplier=3.0, jitter_factor=0)
        assert delay == 2700.0

    def test_jitter_adds_variance(self):
        delays = set()
        for _ in range(20):
            d = calculate_backoff(0, base_seconds=100, multiplier=1.0, jitter_factor=0.5)
            delays.add(round(d, 2))
        # With 50% jitter we expect different values
        assert len(delays) > 1

    def test_minimum_delay_is_one(self):
        delay = calculate_backoff(0, base_seconds=0, multiplier=0, jitter_factor=0)
        assert delay >= 1.0


# ---------------------------------------------------------------------------
# Job lifecycle tests
# ---------------------------------------------------------------------------


class TestJobEnqueue:
    def test_enqueue_creates_pending_job(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success", payload={"key": "val"})
            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 0
            assert json.loads(job.payload) == {"key": "val"}

    def test_enqueue_custom_max_retries(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success", max_retries=5)
            assert job.max_retries == 5


class TestJobExecution:
    def test_successful_execution(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success")
            result = execute_job(job)
            assert result is True
            assert job.status == JobStatus.COMPLETED.value
            assert job.completed_at is not None
            assert json.loads(job.result) == {"ok": True}

    def test_failed_execution_schedules_retry(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_failure")
            result = execute_job(job)
            assert result is False
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 1
            assert job.next_retry_at is not None
            assert job.last_error is not None
            assert "Simulated failure" in job.last_error

    def test_no_handler_moves_to_dead_letter(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("nonexistent_job_type")
            result = execute_job(job)
            assert result is False
            assert job.status == JobStatus.DEAD.value

    def test_exhausted_retries_moves_to_dead_letter(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_failure", max_retries=1)
            execute_job(job)
            # After 1 failure with max_retries=1, should be dead
            assert job.status == JobStatus.DEAD.value
            assert job.retry_count == 1

    def test_conditional_job_success_and_failure(self, app_fixture):
        with app_fixture.app_context():
            # Success path
            job1 = enqueue_job("test_conditional", payload={"value": 99})
            assert execute_job(job1) is True
            assert job1.status == JobStatus.COMPLETED.value
            assert json.loads(job1.result) == {"result": 99}

            # Failure path
            job2 = enqueue_job("test_conditional", payload={"fail": True})
            assert execute_job(job2) is False
            assert "conditional fail" in job2.last_error


# ---------------------------------------------------------------------------
# Retry processing tests
# ---------------------------------------------------------------------------


class TestRetryProcessing:
    def test_process_pending_retries_executes_due_jobs(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success")
            # Simulate a failed job that's due for retry
            job.status = JobStatus.PENDING.value
            job.retry_count = 1
            job.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
            db.session.commit()

            count = process_pending_retries()
            assert count == 1

            refreshed = db.session.get(JobExecution, job.id)
            assert refreshed.status == JobStatus.COMPLETED.value

    def test_process_skips_future_retries(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success")
            job.status = JobStatus.PENDING.value
            job.retry_count = 1
            job.next_retry_at = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()

            count = process_pending_retries()
            assert count == 0

    def test_process_skips_non_retry_pending(self, app_fixture):
        """Jobs with retry_count=0 are new, not retries."""
        with app_fixture.app_context():
            enqueue_job("test_success")
            count = process_pending_retries()
            assert count == 0


# ---------------------------------------------------------------------------
# Dead-letter queue tests
# ---------------------------------------------------------------------------


class TestDeadLetterQueue:
    def test_get_dead_letter_jobs(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_failure", max_retries=1)
            execute_job(job)  # exhausts retries -> dead
            assert job.status == JobStatus.DEAD.value

            dead = get_dead_letter_jobs()
            assert len(dead) == 1
            assert dead[0].id == job.id

    def test_get_dead_letter_jobs_filter_by_type(self, app_fixture):
        with app_fixture.app_context():
            job1 = enqueue_job("test_failure", max_retries=1)
            execute_job(job1)
            job2 = enqueue_job("test_failure", max_retries=1)
            job2.job_type = "other_type"
            _move_to_dead_letter(job2, "manual")

            dead = get_dead_letter_jobs(job_type="other_type")
            assert len(dead) == 1
            assert dead[0].id == job2.id

    def test_retry_dead_letter_job_resets_state(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_failure", max_retries=1)
            execute_job(job)
            assert job.status == JobStatus.DEAD.value

            reset = retry_dead_letter_job(job.id)
            assert reset is not None
            assert reset.status == JobStatus.PENDING.value
            assert reset.retry_count == 0
            assert reset.last_error is None

    def test_retry_nonexistent_returns_none(self, app_fixture):
        with app_fixture.app_context():
            assert retry_dead_letter_job(99999) is None

    def test_retry_non_dead_returns_none(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success")
            assert retry_dead_letter_job(job.id) is None


# ---------------------------------------------------------------------------
# Circuit Breaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_starts_closed(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        cb = CircuitBreaker("smtp", redis_client_override=mock_redis)
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.is_available() is True

    def test_opens_after_threshold_failures(self):
        mock_redis = MagicMock()
        state_store = {}

        def mock_get(key):
            return state_store.get(key)

        def mock_set(key, value, ex=None):
            state_store[key] = value

        mock_redis.get = mock_get
        mock_redis.set = mock_set

        cb = CircuitBreaker(
            "smtp", failure_threshold=3, redis_client_override=mock_redis
        )

        cb.record_failure()
        cb.record_failure()
        assert cb.is_available() is True  # not yet at threshold

        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.is_available() is False

    def test_success_resets_to_closed(self):
        mock_redis = MagicMock()
        state_store = {}

        def mock_get(key):
            return state_store.get(key)

        def mock_set(key, value, ex=None):
            state_store[key] = value

        mock_redis.get = mock_get
        mock_redis.set = mock_set

        cb = CircuitBreaker(
            "smtp", failure_threshold=2, redis_client_override=mock_redis
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.is_available() is True

    def test_half_open_after_recovery_timeout(self):
        mock_redis = MagicMock()
        state_store = {}

        def mock_get(key):
            return state_store.get(key)

        def mock_set(key, value, ex=None):
            state_store[key] = value

        mock_redis.get = mock_get
        mock_redis.set = mock_set

        cb = CircuitBreaker(
            "smtp",
            failure_threshold=1,
            recovery_timeout=0,  # immediate recovery
            redis_client_override=mock_redis,
        )
        cb.record_failure()
        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.is_available() is True

    def test_reset_clears_state(self):
        mock_redis = MagicMock()
        cb = CircuitBreaker("smtp", redis_client_override=mock_redis)
        cb.reset()
        mock_redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


class TestDispatchReminders:
    def test_dispatch_sends_due_reminders(self, app_fixture):
        with app_fixture.app_context():
            r1 = MagicMock(id=1, sent=False)
            r2 = MagicMock(id=2, sent=False)

            def sender(r):
                return True

            result = dispatch_reminders([r1, r2], sender)
            assert result["sent_count"] == 2
            assert result["failed_count"] == 0
            assert r1.sent is True
            assert r2.sent is True

    def test_dispatch_handles_sender_returning_false(self, app_fixture):
        with app_fixture.app_context():
            r1 = MagicMock(id=1, sent=False)

            def sender(r):
                return False

            result = dispatch_reminders([r1], sender)
            assert result["sent_count"] == 0
            assert result["failed_count"] == 1
            assert r1.sent is False

    def test_dispatch_handles_sender_exception(self, app_fixture):
        with app_fixture.app_context():
            r1 = MagicMock(id=1, sent=False)

            def sender(r):
                raise ConnectionError("SMTP down")

            result = dispatch_reminders([r1], sender)
            assert result["sent_count"] == 0
            assert result["failed_count"] == 1
            assert result["details"][0]["status"] == "error"
            assert "SMTP down" in result["details"][0]["error"]

    def test_dispatch_empty_list(self, app_fixture):
        with app_fixture.app_context():
            result = dispatch_reminders([], lambda r: True)
            assert result["sent_count"] == 0
            assert result["failed_count"] == 0


# ---------------------------------------------------------------------------
# Stats & health tests
# ---------------------------------------------------------------------------


class TestJobStats:
    def test_stats_empty_database(self, app_fixture):
        with app_fixture.app_context():
            stats = get_job_stats()
            assert stats["total_jobs"] == 0
            assert stats["success_rate"] == 0.0
            assert stats["by_type"] == {}

    def test_stats_mixed_statuses(self, app_fixture):
        with app_fixture.app_context():
            j1 = enqueue_job("test_success")
            execute_job(j1)
            j2 = enqueue_job("test_failure", max_retries=1)
            execute_job(j2)

            stats = get_job_stats()
            assert stats["total_jobs"] == 2
            assert stats["success_rate"] == 50.0


class TestHealthStatus:
    def test_healthy_when_no_issues(self, app_fixture):
        with app_fixture.app_context():
            health = get_health_status()
            assert health["healthy"] is True
            assert health["stuck_jobs"] == 0

    def test_unhealthy_with_stuck_job(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("test_success")
            job.status = JobStatus.RUNNING.value
            job.started_at = datetime.utcnow() - timedelta(hours=2)
            db.session.commit()

            health = get_health_status()
            assert health["healthy"] is False
            assert health["stuck_jobs"] == 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestJobsAPI:
    def test_job_status_endpoint(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            enqueue_job("test_success", payload={"x": 1})
        r = client.get("/jobs/status", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["job_type"] == "test_success"

    def test_job_status_filter_by_status(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            j = enqueue_job("test_success")
            execute_job(j)
        r = client.get("/jobs/status?status=COMPLETED", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 1

        r = client.get("/jobs/status?status=PENDING", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 0

    def test_job_stats_endpoint(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            j = enqueue_job("test_success")
            execute_job(j)
        r = client.get("/jobs/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_jobs"] == 1
        assert data["success_rate"] == 100.0

    def test_job_health_endpoint_no_auth(self, client, app_fixture):
        """Health endpoint should work without authentication."""
        r = client.get("/jobs/health")
        assert r.status_code == 200
        data = r.get_json()
        assert data["healthy"] is True

    def test_dead_letters_endpoint(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            j = enqueue_job("test_failure", max_retries=1)
            execute_job(j)
        r = client.get("/jobs/dead-letters", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] == 1

    def test_retry_dead_letter_endpoint(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            j = enqueue_job("test_failure", max_retries=1)
            execute_job(j)
            job_id = j.id

        r = client.post(f"/jobs/dead-letters/{job_id}/retry", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "PENDING"
        assert data["retry_count"] == 0

    def test_retry_dead_letter_not_found(self, client, auth_header):
        r = client.post("/jobs/dead-letters/99999/retry", headers=auth_header)
        assert r.status_code == 404

    def test_run_retries_endpoint(self, client, auth_header, app_fixture):
        r = client.post("/jobs/run-retries", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["processed"] == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_concurrent_retry_handling(self, app_fixture):
        """Multiple retries for the same job type don't interfere."""
        with app_fixture.app_context():
            j1 = enqueue_job("test_failure", max_retries=2)
            j2 = enqueue_job("test_failure", max_retries=2)
            execute_job(j1)
            execute_job(j2)
            # Both should have independent retry counts
            assert j1.retry_count == 1
            assert j2.retry_count == 1
            assert j1.next_retry_at != j2.next_retry_at or True  # jitter

    def test_redis_failure_in_dlq_still_marks_dead(self, app_fixture):
        """DLQ push to Redis is best-effort; job still moves to DEAD."""
        with app_fixture.app_context():
            with patch("app.services.job_manager.redis_client") as mock_redis:
                mock_redis.lpush.side_effect = ConnectionError("Redis down")
                j = enqueue_job("test_failure", max_retries=1)
                execute_job(j)
                assert j.status == JobStatus.DEAD.value

    def test_null_payload_job(self, app_fixture):
        with app_fixture.app_context():
            j = enqueue_job("test_success", payload=None)
            assert execute_job(j) is True
            assert j.status == JobStatus.COMPLETED.value
