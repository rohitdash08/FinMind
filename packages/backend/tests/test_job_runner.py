"""Tests for background job runner."""

import pytest
from app.services.job_runner import (
    enqueue, execute, process_pending, get_monitoring_stats,
    register_handler, BackgroundJob, JobStatus,
)


def succeed_handler(payload):
    pass

def fail_handler(payload):
    raise RuntimeError("intentional failure")


class TestJobRunner:
    @pytest.fixture(autouse=True)
    def setup(self, app, db_session):
        register_handler("test_succeed", succeed_handler)
        register_handler("test_fail", fail_handler)

    def test_enqueue_creates_pending_job(self, app):
        with app.app_context():
            job = enqueue("test_succeed")
            assert job.status == JobStatus.PENDING.value
            assert job.attempts == 0

    def test_execute_success(self, app):
        with app.app_context():
            job = enqueue("test_succeed")
            result = execute(job)
            assert result["status"] == "completed"
            assert job.status == JobStatus.COMPLETED.value

    def test_execute_failure_with_retry(self, app):
        with app.app_context():
            job = enqueue("test_fail", max_retries=3)
            result = execute(job)
            assert result["status"] == "failed"
            assert job.attempts == 1
            assert job.next_retry_at is not None

    def test_dead_letter_after_max_retries(self, app):
        with app.app_context():
            job = enqueue("test_fail", max_retries=2)
            execute(job)
            execute(job)
            assert job.status == JobStatus.DEAD_LETTERED.value
            assert job.attempts == 2

    def test_no_handler_dead_letters(self, app):
        with app.app_context():
            job = enqueue("nonexistent_handler")
            result = execute(job)
            assert result["status"] == "dead_lettered"

    def test_process_pending(self, app):
        with app.app_context():
            enqueue("test_succeed")
            enqueue("test_succeed")
            results = process_pending()
            assert len(results) == 2
            assert all(r["status"] == "completed" for r in results)

    def test_monitoring_stats(self, app):
        with app.app_context():
            enqueue("test_succeed")
            enqueue("test_fail")
            process_pending()
            stats = get_monitoring_stats(hours=1)
            assert stats["total_jobs"] == 2
            assert stats["completed"] == 1
            assert stats["failed"] == 1

    def test_exponential_backoff(self, app):
        with app.app_context():
            job = enqueue("test_fail", max_retries=5, backoff_factor=2.0)
            execute(job)
            first_retry = job.next_retry_at
            execute(job)
            second_retry = job.next_retry_at
            assert second_retry > first_retry

    def test_monitoring_alert_on_high_failure(self, app):
        with app.app_context():
            for _ in range(5):
                enqueue("test_fail")
            process_pending()
            stats = get_monitoring_stats(hours=1)
            assert stats["alert"] is True
