"""
Tests for background job retry service and monitoring endpoints.
Covers: enqueue, success, retry with backoff, dead-letter, requeue, cancel, stats.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
import pytest

from app.models import BackgroundJob, JobStatus
from app.services.job_service import (
    _calculate_backoff,
    cancel_job,
    enqueue_job,
    execute_job,
    get_dead_letter_jobs,
    get_job_stats,
    get_pending_jobs,
    requeue_dead_job,
)


# --- Unit tests for backoff calculation ---

class TestCalculateBackoff:
    def test_first_attempt(self):
        assert _calculate_backoff(0) == 5   # 5 * 2^0 = 5

    def test_second_attempt(self):
        assert _calculate_backoff(1) == 10  # 5 * 2^1 = 10

    def test_third_attempt(self):
        assert _calculate_backoff(2) == 20  # 5 * 2^2 = 20

    def test_max_cap(self):
        assert _calculate_backoff(100, max_delay=300) == 300

    def test_custom_base(self):
        assert _calculate_backoff(1, base_delay=10) == 20


# --- Integration-style tests using in-memory SQLite ---

@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield


@pytest.fixture
def sample_job(app_ctx, db):
    job = BackgroundJob(
        job_type="test_job",
        payload=json.dumps({"key": "value"}),
        status=JobStatus.PENDING.value,
        max_retries=3,
        attempt_count=0,
        next_retry_at=datetime.utcnow() - timedelta(seconds=1),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    return job


class TestExecuteJob:
    def test_success_marks_completed(self, sample_job):
        handler = MagicMock()
        result = execute_job(sample_job, handler)
        assert result is True
        assert sample_job.status == JobStatus.COMPLETED.value
        assert sample_job.attempt_count == 1
        assert sample_job.completed_at is not None
        handler.assert_called_once_with({"key": "value"})

    def test_failure_increments_attempts_and_schedules_retry(self, sample_job):
        def failing_handler(payload):
            raise ValueError("test error")

        result = execute_job(sample_job, failing_handler)
        assert result is False
        assert sample_job.status == JobStatus.RETRYING.value
        assert sample_job.attempt_count == 1
        assert sample_job.error_log is not None
        assert "test error" in sample_job.error_log
        assert sample_job.next_retry_at > datetime.utcnow()

    def test_max_retries_moves_to_dead(self, sample_job):
        sample_job.attempt_count = 2  # already at max - 1
        sample_job.max_retries = 3

        def failing_handler(payload):
            raise RuntimeError("fatal error")

        result = execute_job(sample_job, failing_handler)
        assert result is False
        assert sample_job.status == JobStatus.DEAD.value

    def test_error_log_accumulates(self, sample_job):
        def failing_handler(payload):
            raise ValueError("error one")

        execute_job(sample_job, failing_handler)
        error_log_after_first = sample_job.error_log

        sample_job.status = JobStatus.RETRYING.value
        sample_job.next_retry_at = datetime.utcnow() - timedelta(seconds=1)

        def failing_handler2(payload):
            raise ValueError("error two")

        execute_job(sample_job, failing_handler2)
        assert "error one" in sample_job.error_log
        assert "error two" in sample_job.error_log


class TestGetPendingJobs:
    def test_returns_pending_jobs(self, sample_job):
        jobs = get_pending_jobs()
        assert any(j.id == sample_job.id for j in jobs)

    def test_does_not_return_future_retries(self, sample_job, db):
        future_job = BackgroundJob(
            job_type="future",
            payload="{}",
            status=JobStatus.RETRYING.value,
            attempt_count=1,
            max_retries=3,
            next_retry_at=datetime.utcnow() + timedelta(hours=1),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(future_job)
        db.session.commit()
        jobs = get_pending_jobs()
        assert not any(j.id == future_job.id for j in jobs)


class TestRequeueAndCancel:
    def test_requeue_dead_job(self, sample_job):
        sample_job.status = JobStatus.DEAD.value
        from app.extensions import db
        db.session.commit()
        result = requeue_dead_job(sample_job.id)
        assert result is not None
        assert result.status == JobStatus.PENDING.value
        assert result.attempt_count == 0

    def test_requeue_non_dead_returns_none(self, sample_job):
        result = requeue_dead_job(sample_job.id)
        assert result is None

    def test_cancel_pending_job(self, sample_job):
        success = cancel_job(sample_job.id)
        assert success is True
        assert sample_job.status == JobStatus.CANCELLED.value

    def test_cancel_completed_job_fails(self, sample_job):
        sample_job.status = JobStatus.COMPLETED.value
        from app.extensions import db
        db.session.commit()
        success = cancel_job(sample_job.id)
        assert success is False


class TestJobStats:
    def test_stats_returns_all_statuses(self, sample_job):
        stats = get_job_stats()
        for status in JobStatus:
            assert status.value in stats
        assert stats[JobStatus.PENDING.value] >= 1


class TestJobEndpoints:
    def test_list_jobs_requires_auth(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 401

    def test_stats_requires_auth(self, client):
        resp = client.get("/api/jobs/stats")
        assert resp.status_code == 401

    def test_list_jobs_authenticated(self, auth_client, sample_job):
        resp = auth_client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "total" in data

    def test_dead_letter_queue(self, auth_client, db):
        from app.extensions import db as _db
        dead_job = BackgroundJob(
            job_type="dead",
            payload="{}",
            status=JobStatus.DEAD.value,
            attempt_count=3,
            max_retries=3,
            next_retry_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        _db.session.add(dead_job)
        _db.session.commit()
        resp = auth_client.get("/api/jobs/dead-letter")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] >= 1
