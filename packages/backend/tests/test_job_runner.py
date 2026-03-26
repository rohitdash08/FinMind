"""Tests for the resilient background job runner."""

import pytest
from datetime import datetime, timedelta

from app.models import BackgroundJob, JobStatus
from app.services.job_runner import JobRunner, JobResult, RetryPolicy
from app.extensions import db


@pytest.fixture
def runner():
    """Fresh job runner instance."""
    return JobRunner(RetryPolicy(max_retries=3, base_delay_seconds=1, max_delay_seconds=10))


@pytest.fixture
def setup_handler(runner):
    """Register a simple test handler."""
    call_log = []

    def handler(should_fail=False, message="ok", **_kw):
        call_log.append({"should_fail": should_fail})
        if should_fail:
            return JobResult(success=False, error_message=message)
        return JobResult(success=True, metadata={"msg": message})

    runner.register_handler("test_job", handler)
    return handler, call_log


@pytest.fixture
def app(app_fixture):
    """Alias for existing conftest app_fixture."""
    return app_fixture


class TestRetryPolicy:
    def test_exponential_backoff(self):
        policy = RetryPolicy(base_delay_seconds=5, backoff_multiplier=2.0, max_delay_seconds=300)
        assert policy.delay_for_attempt(0) == 5
        assert policy.delay_for_attempt(1) == 10
        assert policy.delay_for_attempt(2) == 20
        assert policy.delay_for_attempt(3) == 40

    def test_max_delay_cap(self):
        policy = RetryPolicy(base_delay_seconds=60, backoff_multiplier=10.0, max_delay_seconds=120)
        assert policy.delay_for_attempt(0) == 60
        assert policy.delay_for_attempt(1) == 120  # capped
        assert policy.delay_for_attempt(5) == 120  # still capped


class TestJobRunnerEnqueue:
    def test_enqueue_creates_pending_job(self, app, runner, setup_handler):
        with app.app_context():
            job = runner.enqueue("test_job", payload={"message": "hello"})
            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.attempts == 0
            assert job.payload == {"message": "hello"}

    def test_enqueue_custom_max_retries(self, app, runner, setup_handler):
        with app.app_context():
            job = runner.enqueue("test_job", payload={}, max_retries=7)
            assert job.max_retries == 7


class TestJobRunnerExecution:
    def test_successful_execution(self, app, runner, setup_handler):
        _, call_log = setup_handler
        with app.app_context():
            job = runner.enqueue("test_job", payload={"message": "works"})
            db_job_id = job.id

            processed = runner.process_due_jobs()
            assert processed == 1

            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.COMPLETED.value
            assert job.attempts == 1
            assert job.completed_at is not None

    def test_retry_on_failure(self, app, runner, setup_handler):
        _, call_log = setup_handler
        with app.app_context():
            job = runner.enqueue("test_job", payload={"should_fail": True, "message": "transient error"})
            db_job_id = job.id

            # First attempt fails -> RETRYING
            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.RETRYING.value
            assert job.attempts == 1
            assert job.next_retry_at is not None
            assert "transient error" in job.error_message

    def test_dead_after_max_retries(self, app, runner, setup_handler):
        _, call_log = setup_handler
        with app.app_context():
            job = runner.enqueue("test_job", payload={"should_fail": True, "message": "perm fail"}, max_retries=2)
            db_job_id = job.id

            # Attempt 1 -> RETRYING
            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.RETRYING.value

            # Force next retry to be due
            job.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

            # Attempt 2 -> DEAD (max_retries=2, attempts now 2)
            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.DEAD.value
            assert job.attempts == 2
            assert job.completed_at is not None

    def test_succeeds_after_retries(self, app, runner):
        """Simulate a job that fails twice then succeeds."""
        attempt_counter = {"n": 0}

        def flaky_handler(**_kw):
            attempt_counter["n"] += 1
            if attempt_counter["n"] < 3:
                return JobResult(success=False, error_message="not yet")
            return JobResult(success=True, metadata={"attempt": attempt_counter["n"]})

        runner.register_handler("flaky", flaky_handler)

        with app.app_context():
            job = runner.enqueue("flaky", payload={})
            db_job_id = job.id

            # Attempt 1 -> RETRYING
            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.RETRYING.value

            # Force retry
            job.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

            # Attempt 2 -> RETRYING
            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.RETRYING.value

            # Force retry
            job.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

            # Attempt 3 -> COMPLETED
            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.COMPLETED.value
            assert job.attempts == 3

    def test_no_handler_marks_failed(self, app, runner):
        with app.app_context():
            job = runner.enqueue("unknown_type", payload={})
            db_job_id = job.id

            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.FAILED.value
            assert "No handler" in job.error_message


class TestJobRunnerMonitoring:
    def test_get_stats(self, app, runner, setup_handler):
        with app.app_context():
            runner.enqueue("test_job", payload={"message": "ok"})
            runner.enqueue("test_job", payload={"should_fail": True, "message": "fail"}, max_retries=1)
            runner.process_due_jobs()

            # Force the failed one to exhaust retries
            job = BackgroundJob.query.filter_by(status=JobStatus.RETRYING.value).first()
            if job:
                job.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
                db.session.commit()
                runner.process_due_jobs()

            stats = runner.get_stats()
            assert "by_status" in stats
            assert "total" in stats
            assert stats["total"] >= 2

    def test_retry_dead_job(self, app, runner, setup_handler):
        with app.app_context():
            job = runner.enqueue("test_job", payload={"should_fail": True, "message": "x"}, max_retries=1)
            db_job_id = job.id

            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            job.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

            runner.process_due_jobs()
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.DEAD.value

            # Manual retry
            ok = runner.retry_dead_job(db_job_id)
            assert ok
            job = db.session.get(BackgroundJob, db_job_id)
            assert job.status == JobStatus.PENDING.value
