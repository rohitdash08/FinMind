"""Tests for the resilient job retry system."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.models.job_execution import JobExecution, JobStatus
from app.services.job_retry import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    compute_backoff,
    execute_with_retry,
    get_job_stats,
    get_recent_executions,
    register_alert_callback,
    _alert_callbacks,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_alert_callbacks():
    """Ensure alert callbacks don't leak between tests."""
    original = _alert_callbacks.copy()
    yield
    _alert_callbacks.clear()
    _alert_callbacks.extend(original)


# ---------------------------------------------------------------------------
# Backoff tests
# ---------------------------------------------------------------------------
class TestComputeBackoff:
    def test_first_attempt_near_base(self):
        delay = compute_backoff(0, base=10, cap=600)
        # With 25% jitter: 7.5 – 12.5
        assert 5 <= delay <= 15

    def test_exponential_growth(self):
        d0 = compute_backoff(0, base=10, cap=600)
        d2 = compute_backoff(2, base=10, cap=600)
        # Attempt 2 → base * 4 = 40, so should be much larger than attempt 0
        assert d2 > d0

    def test_cap_respected(self):
        delay = compute_backoff(20, base=10, cap=100)
        # Even with jitter, should not exceed cap + 25%
        assert delay <= 100 * 1.30

    def test_never_negative(self):
        for attempt in range(10):
            assert compute_backoff(attempt) >= 0


# ---------------------------------------------------------------------------
# execute_with_retry tests
# ---------------------------------------------------------------------------
class TestExecuteWithRetry:
    def test_success_on_first_try(self, app_fixture):
        fn = MagicMock(return_value=None)
        with app_fixture.app_context():
            result = execute_with_retry(
                fn, job_name="test_success", max_retries=3, backoff_base=0.01,
                app=app_fixture,
            )
        assert result.status == JobStatus.SUCCESS
        assert result.attempt == 1
        assert result.duration_ms is not None
        assert result.error_message is None
        fn.assert_called_once()

    def test_retry_then_success(self, app_fixture):
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("transient failure")

        with app_fixture.app_context():
            result = execute_with_retry(
                flaky, job_name="test_flaky", max_retries=3, backoff_base=0.01,
                app=app_fixture,
            )
        assert result.status == JobStatus.SUCCESS
        assert result.attempt == 3
        assert call_count["n"] == 3

    def test_dead_after_max_retries(self, app_fixture):
        fn = MagicMock(side_effect=ValueError("permanent error"))
        with app_fixture.app_context():
            result = execute_with_retry(
                fn, job_name="test_dead", max_retries=2, backoff_base=0.01,
                app=app_fixture,
            )
        assert result.status == JobStatus.DEAD
        assert result.attempt == 3  # 1 initial + 2 retries
        assert "permanent error" in result.error_message
        assert fn.call_count == 3

    def test_error_traceback_captured(self, app_fixture):
        def bad():
            raise TypeError("type issue")

        with app_fixture.app_context():
            result = execute_with_retry(
                bad, job_name="test_tb", max_retries=0, backoff_base=0.01,
                app=app_fixture,
            )
        assert result.status == JobStatus.DEAD
        assert "TypeError" in result.error_traceback

    def test_alert_fired_on_failure(self, app_fixture):
        alert_mock = MagicMock()
        register_alert_callback(alert_mock)

        with app_fixture.app_context():
            execute_with_retry(
                MagicMock(side_effect=RuntimeError("boom")),
                job_name="test_alert",
                max_retries=1,
                backoff_base=0.01,
                app=app_fixture,
            )
        # Called on RETRYING + DEAD = 2 times
        assert alert_mock.call_count == 2

    def test_execution_persisted_to_db(self, app_fixture):
        with app_fixture.app_context():
            execute_with_retry(
                lambda: None,
                job_name="test_persist",
                max_retries=0,
                backoff_base=0.01,
                app=app_fixture,
            )
            rows = JobExecution.query.filter_by(job_name="test_persist").all()
            assert len(rows) == 1
            assert rows[0].status == JobStatus.SUCCESS


# ---------------------------------------------------------------------------
# Query helper tests
# ---------------------------------------------------------------------------
class TestQueryHelpers:
    def _seed(self, app_fixture, statuses):
        with app_fixture.app_context():
            for i, s in enumerate(statuses):
                e = JobExecution(
                    job_id=f"seed_{i}",
                    job_name="seeded",
                    status=s,
                    attempt=1,
                    max_retries=3,
                )
                db.session.add(e)
            db.session.commit()

    def test_get_recent_executions_limit(self, app_fixture):
        self._seed(app_fixture, [JobStatus.SUCCESS] * 5)
        with app_fixture.app_context():
            results = get_recent_executions(limit=3)
            assert len(results) == 3

    def test_get_recent_executions_filter_status(self, app_fixture):
        self._seed(
            app_fixture,
            [JobStatus.SUCCESS, JobStatus.DEAD, JobStatus.SUCCESS],
        )
        with app_fixture.app_context():
            results = get_recent_executions(status="DEAD")
            assert all(r.status == JobStatus.DEAD for r in results)

    def test_get_job_stats(self, app_fixture):
        self._seed(
            app_fixture,
            [JobStatus.SUCCESS, JobStatus.SUCCESS, JobStatus.DEAD],
        )
        with app_fixture.app_context():
            stats = get_job_stats()
            assert stats["SUCCESS"] == 2
            assert stats["DEAD"] == 1
            assert stats["total"] == 3


# ---------------------------------------------------------------------------
# Decorator tests
# ---------------------------------------------------------------------------
class TestResilientJobDecorator:
    def test_decorator_wraps_function(self, app_fixture):
        from app.services.job_retry import resilient_job

        @resilient_job(max_retries=1, backoff_base=0.01)
        def my_task():
            return "done"

        with app_fixture.app_context():
            result = my_task()
        assert result.status == JobStatus.SUCCESS
        assert result.job_name == "my_task"
