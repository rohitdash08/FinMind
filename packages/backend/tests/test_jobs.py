"""Tests for the resilient background job retry & monitoring system."""
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from app.extensions import db
from app.services.jobs import (
    AsyncJob,
    JobRunner,
    JobStatus,
    register_handler,
    process_retry_queue,
)


class TestAsyncJobModel:
    """Unit tests for the AsyncJob model."""

    def test_create_job(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job", payload=json.dumps({"key": "value"}))
            db.session.add(job)
            db.session.commit()

            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.attempt == 0
            assert job.max_attempts == 3

    def test_mark_running(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job")
            db.session.add(job)
            db.session.commit()

            job.mark_running()
            assert job.status == JobStatus.RUNNING.value
            assert job.attempt == 1
            assert job.started_at is not None

    def test_mark_success(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job")
            db.session.add(job)
            db.session.commit()
            job.mark_running()

            time.sleep(0.01)  # ensure measurable duration
            job.mark_success(result_data='{"ok": true}')

            assert job.status == JobStatus.SUCCESS.value
            assert job.completed_at is not None
            assert job.duration_ms is not None and job.duration_ms > 0
            assert job.result == '{"ok": true}'
            assert job.next_retry_at is None

    def test_mark_failed_with_retry(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job", max_attempts=3)
            db.session.add(job)
            db.session.commit()
            job.mark_running()

            job.mark_failed("Something broke", schedule_retry=True)

            assert job.status == JobStatus.RETRYING.value
            assert job.last_error == "Something broke"
            assert job.attempt == 1
            assert job.next_retry_at is not None
            assert job.next_retry_at > datetime.utcnow()

    def test_mark_failed_exhausted(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job", max_attempts=1)
            db.session.add(job)
            db.session.commit()
            job.mark_running()

            job.mark_failed("Final failure", schedule_retry=True)

            assert job.status == JobStatus.FAILED.value
            assert job.next_retry_at is None

    def test_cancel(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job")
            db.session.add(job)
            db.session.commit()
            job.cancel()
            assert job.status == JobStatus.CANCELLED.value
            assert job.next_retry_at is None

    def test_to_dict(self, app):
        with app.app_context():
            job = AsyncJob(job_type="test_job")
            db.session.add(job)
            db.session.commit()
            d = job.to_dict()
            assert d["id"] == job.id
            assert d["job_type"] == "test_job"
            assert d["status"] == JobStatus.PENDING.value


class TestJobRunner:
    """Tests for the JobRunner."""

    def test_successful_run(self, app):
        @register_handler("success_handler")
        def success_handler(payload):
            return "done"

        with app.app_context():
            runner = JobRunner(success_handler)
            job = runner.run(payload="")
            assert job.status == JobStatus.SUCCESS.value
            assert job.result == "done"

    def test_failed_run_with_retry(self, app):
        call_count = 0

        @register_handler("flaky_handler")
        def flaky_handler(payload):
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Attempt {call_count} failed")

        with app.app_context():
            runner = JobRunner(flaky_handler, max_attempts=3)
            job = runner.run(payload="")
            assert job.status == JobStatus.RETRYING.value
            assert job.attempt == 1  # first attempt failed
            assert "Attempt 1 failed" in job.last_error
            assert job.next_retry_at is not None


class TestRetryQueue:
    """Tests for the retry queue processing."""

    def test_process_retry_queue(self, app):
        with app.app_context():
            # Create a job that is due for retry
            job = AsyncJob(
                job_type="missing_handler",
                status=JobStatus.RETRYING.value,
                attempt=1,
                max_attempts=3,
                next_retry_at=datetime.utcnow() - timedelta(minutes=5),
            )
            db.session.add(job)
            db.session.commit()

            count = process_retry_queue(max_jobs=10)
            assert count == 1

            # Reload and check it failed without handler
            db.session.refresh(job)
            assert job.status == JobStatus.FAILED.value

    def test_retry_honours_max(self, app):
        with app.app_context():
            for i in range(5):
                job = AsyncJob(
                    job_type="test",
                    status=JobStatus.RETRYING.value,
                    attempt=1,
                    max_attempts=3,
                    next_retry_at=datetime.utcnow() - timedelta(minutes=1),
                )
                db.session.add(job)
            db.session.commit()

            count = process_retry_queue(max_jobs=3)
            assert count == 3  # Only 3 out of 5 due
