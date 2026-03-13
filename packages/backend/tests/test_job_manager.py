"""Tests for the resilient background job manager."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.job_manager import (
    JobExecution,
    JobManager,
    JobState,
    JobStatus,
    RetryPolicy,
    job_manager,
)


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    def test_default_values(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.base_delay_seconds == 5.0
        assert p.backoff_factor == 2.0

    def test_delay_exponential_backoff(self):
        p = RetryPolicy(base_delay_seconds=1.0, backoff_factor=2.0)
        assert p.delay_for_attempt(0) == 1.0
        assert p.delay_for_attempt(1) == 2.0
        assert p.delay_for_attempt(2) == 4.0
        assert p.delay_for_attempt(3) == 8.0

    def test_delay_capped_at_max(self):
        p = RetryPolicy(base_delay_seconds=100.0, max_delay_seconds=300.0, backoff_factor=10.0)
        assert p.delay_for_attempt(0) == 100.0
        assert p.delay_for_attempt(1) == 300.0  # capped
        assert p.delay_for_attempt(5) == 300.0  # still capped


# ---------------------------------------------------------------------------
# JobState
# ---------------------------------------------------------------------------

class TestJobState:
    def test_record_caps_history(self):
        state = JobState(job_id="test")
        state.MAX_HISTORY = 5
        for i in range(10):
            exe = JobExecution(
                job_id="test",
                attempt=i,
                status="success",
                started_at=f"2026-01-01T00:0{i}:00",
            )
            state.record(exe)
        assert len(state.history) == 5
        # Should keep the last 5
        assert state.history[0]["attempt"] == 5


# ---------------------------------------------------------------------------
# JobManager unit tests (no Flask app)
# ---------------------------------------------------------------------------

class TestJobManagerUnit:
    def test_add_and_get_status(self):
        mgr = JobManager()
        mgr._scheduler = MagicMock()
        mgr._scheduler.running = False
        mgr._metrics = None

        def dummy():
            pass

        mgr.add_job(dummy, job_id="test_job", trigger="interval", seconds=60)

        status = mgr.get_status()
        assert "test_job" in status
        assert status["test_job"]["status"] == "pending"
        assert status["test_job"]["max_retries"] == 3  # default

    def test_dead_letters_empty_initially(self):
        mgr = JobManager()
        assert mgr.get_dead_letters() == []

    def test_dead_letters_after_failure(self):
        mgr = JobManager()
        mgr._states["broken"] = JobState(
            job_id="broken",
            last_status=JobStatus.FAILED.value,
            last_error="kaboom",
            total_failures=3,
        )
        dead = mgr.get_dead_letters()
        assert len(dead) == 1
        assert dead[0]["job_id"] == "broken"
        assert dead[0]["last_error"] == "kaboom"

    def test_reset_job(self):
        mgr = JobManager()
        mgr._states["broken"] = JobState(
            job_id="broken",
            last_status=JobStatus.FAILED.value,
            attempt=3,
            last_error="kaboom",
        )
        assert mgr.reset_job("broken") is True
        state = mgr._states["broken"]
        assert state.last_status == JobStatus.PENDING.value
        assert state.attempt == 0
        assert state.last_error is None

    def test_reset_nonexistent_job(self):
        mgr = JobManager()
        assert mgr.reset_job("nope") is False


# ---------------------------------------------------------------------------
# Integration with Flask app
# ---------------------------------------------------------------------------

class TestJobManagerIntegration:
    @pytest.fixture()
    def managed_app(self, app_fixture):
        """App with a separate job manager (not the global one)."""
        # The global job_manager is already initialized via create_app
        return app_fixture

    def test_job_health_endpoint(self, managed_app):
        with managed_app.test_client() as client:
            resp = client.get("/jobs/health")
            assert resp.status_code in (200, 503)
            data = resp.get_json()
            assert "healthy" in data
            assert "jobs" in data

    @patch("app.routes.auth.redis_client")
    def test_job_status_requires_admin(self, mock_redis, managed_app):
        mock_redis.setex = MagicMock()
        mock_redis.get = MagicMock(return_value=None)
        with managed_app.test_client() as client:
            # Register and login as regular user
            client.post("/auth/register", json={
                "email": "user@test.com", "password": "pass1234"
            })
            resp = client.post("/auth/login", json={
                "email": "user@test.com", "password": "pass1234"
            })
            token = resp.get_json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.get("/jobs/status", headers=headers)
            assert resp.status_code == 403

    @patch("app.routes.auth.redis_client")
    def test_job_dead_letters_requires_admin(self, mock_redis, managed_app):
        mock_redis.setex = MagicMock()
        mock_redis.get = MagicMock(return_value=None)
        with managed_app.test_client() as client:
            client.post("/auth/register", json={
                "email": "user2@test.com", "password": "pass1234"
            })
            resp = client.post("/auth/login", json={
                "email": "user2@test.com", "password": "pass1234"
            })
            token = resp.get_json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.get("/jobs/dead-letters", headers=headers)
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Retry logic simulation
# ---------------------------------------------------------------------------

class TestRetryExecution:
    def test_successful_job_resets_attempt(self):
        mgr = JobManager()
        mgr._scheduler = MagicMock()
        mgr._scheduler.running = False
        mgr._metrics = None
        mgr._app = None

        call_count = 0

        def succeeding_job():
            nonlocal call_count
            call_count += 1

        mgr.add_job(succeeding_job, job_id="good_job", trigger="interval", seconds=60)

        # Simulate execution by calling the wrapped function
        jobs = mgr._scheduler.add_job.call_args_list
        wrapped_fn = jobs[0][0][0]  # first positional arg to add_job
        wrapped_fn()

        state = mgr._states["good_job"]
        assert state.last_status == JobStatus.SUCCESS.value
        assert state.attempt == 0
        assert state.total_successes == 1
        assert call_count == 1

    def test_failing_job_retries_then_dead_letters(self):
        mgr = JobManager()
        mgr._scheduler = MagicMock()
        mgr._scheduler.running = False
        mgr._metrics = None
        mgr._app = None

        def failing_job():
            raise ValueError("boom")

        policy = RetryPolicy(max_retries=2, base_delay_seconds=0.01)
        mgr.add_job(failing_job, job_id="bad_job", trigger="interval",
                     retry_policy=policy, seconds=60)

        jobs = mgr._scheduler.add_job.call_args_list
        wrapped_fn = jobs[0][0][0]

        # First attempt → retrying
        wrapped_fn()
        state = mgr._states["bad_job"]
        assert state.last_status == JobStatus.RETRYING.value
        assert state.attempt == 1

        # Second attempt → dead-lettered
        wrapped_fn()
        assert state.last_status == JobStatus.FAILED.value
        assert state.attempt == 2
        assert "ValueError: boom" in state.last_error

        # Dead-lettered jobs are skipped
        wrapped_fn()
        assert state.total_runs == 2  # didn't increment

    def test_job_recovers_after_transient_failure(self):
        mgr = JobManager()
        mgr._scheduler = MagicMock()
        mgr._scheduler.running = False
        mgr._metrics = None
        mgr._app = None

        call_count = 0

        def flaky_job():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")

        policy = RetryPolicy(max_retries=3, base_delay_seconds=0.01)
        mgr.add_job(flaky_job, job_id="flaky", trigger="interval",
                     retry_policy=policy, seconds=60)

        jobs = mgr._scheduler.add_job.call_args_list
        wrapped_fn = jobs[0][0][0]

        # First: fail
        wrapped_fn()
        state = mgr._states["flaky"]
        assert state.last_status == JobStatus.RETRYING.value

        # Second: succeed
        wrapped_fn()
        assert state.last_status == JobStatus.SUCCESS.value
        assert state.attempt == 0  # reset on success
        assert state.total_successes == 1
        assert state.total_failures == 1


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------

class TestRedisPersistence:
    def test_persist_and_restore(self):
        mock_redis = MagicMock()
        stored = {}

        def mock_set(key, value, **kwargs):
            stored[key] = value

        def mock_get(key):
            return stored.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        # Persist
        mgr1 = JobManager()
        mgr1._redis = mock_redis
        mgr1._states["test"] = JobState(
            job_id="test",
            attempt=2,
            last_status=JobStatus.RETRYING.value,
            total_runs=5,
        )
        mgr1._persist_state()

        # Restore
        mgr2 = JobManager()
        mgr2._redis = mock_redis
        mgr2._restore_state()

        assert "test" in mgr2._states
        assert mgr2._states["test"].attempt == 2
        assert mgr2._states["test"].total_runs == 5

    def test_running_state_recovered_as_retrying(self):
        """If the process crashed mid-run, state should be RETRYING not RUNNING."""
        mock_redis = MagicMock()
        import json
        mock_redis.get.return_value = json.dumps({
            "crashed_job": {
                "job_id": "crashed_job",
                "attempt": 1,
                "last_status": "running",
                "last_error": None,
                "last_run_at": None,
                "next_retry_at": None,
                "total_runs": 3,
                "total_failures": 0,
                "total_successes": 2,
                "history": [],
            }
        })

        mgr = JobManager()
        mgr._redis = mock_redis
        mgr._restore_state()

        assert mgr._states["crashed_job"].last_status == JobStatus.RETRYING.value
