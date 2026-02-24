"""Tests for resilient background job retry & monitoring (#130)."""

import pytest
from app.services.job_queue import (
    BackgroundJob, JobStatus, register_handler, enqueue, process_pending, get_job_stats,
)
from app.extensions import db


# ── Helpers ──────────────────────────────────────────────────────────

def _success_handler(payload):
    """A handler that always succeeds."""
    pass


def _fail_handler(payload):
    """A handler that always fails."""
    raise RuntimeError("intentional failure")


_call_count = 0

def _fail_then_succeed(payload):
    """Fails on first call, succeeds on second."""
    global _call_count
    _call_count += 1
    if _call_count <= payload.get("fail_times", 1):
        raise RuntimeError(f"fail #{_call_count}")


@pytest.fixture(autouse=True)
def _register_handlers(app):
    register_handler("test_success", _success_handler)
    register_handler("test_fail", _fail_handler)
    register_handler("test_retry", _fail_then_succeed)
    global _call_count
    _call_count = 0
    yield


# ── Unit tests ───────────────────────────────────────────────────────

class TestEnqueue:
    def test_creates_pending_job(self, app):
        with app.app_context():
            job = enqueue("test_success", {"key": "val"})
            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.attempts == 0
            assert job.payload == {"key": "val"}

    def test_unknown_handler_raises(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match="No handler"):
                enqueue("nonexistent")


class TestProcessing:
    def test_success_job(self, app):
        with app.app_context():
            job = enqueue("test_success")
            count = process_pending()
            assert count == 1
            db.session.refresh(job)
            assert job.status == JobStatus.COMPLETED.value
            assert job.attempts == 1
            assert job.completed_at is not None
            assert job.last_error is None

    def test_failed_job_retries(self, app):
        with app.app_context():
            job = enqueue("test_fail", max_retries=3)
            process_pending()
            db.session.refresh(job)
            assert job.status == JobStatus.RETRYING.value
            assert job.attempts == 1
            assert job.next_retry_at is not None
            assert "intentional failure" in job.last_error

    def test_permanent_failure_after_max_retries(self, app):
        with app.app_context():
            job = enqueue("test_fail", max_retries=1)
            # First attempt
            process_pending()
            db.session.refresh(job)
            assert job.status == JobStatus.FAILED.value
            assert job.attempts == 1

    def test_retry_then_succeed(self, app):
        with app.app_context():
            job = enqueue("test_retry", {"fail_times": 1}, max_retries=3)
            # First attempt - fails
            process_pending()
            db.session.refresh(job)
            assert job.status == JobStatus.RETRYING.value
            # Force next_retry_at to now so it gets picked up
            job.next_retry_at = None
            db.session.commit()
            # Second attempt - succeeds
            process_pending()
            db.session.refresh(job)
            assert job.status == JobStatus.COMPLETED.value
            assert job.attempts == 2

    def test_no_pending_jobs(self, app):
        with app.app_context():
            count = process_pending()
            assert count == 0


class TestStats:
    def test_empty_stats(self, app):
        with app.app_context():
            stats = get_job_stats()
            assert stats["total"] == 0

    def test_stats_after_jobs(self, app):
        with app.app_context():
            enqueue("test_success")
            enqueue("test_fail", max_retries=1)
            process_pending()
            stats = get_job_stats()
            assert stats[JobStatus.COMPLETED.value] == 1
            assert stats[JobStatus.FAILED.value] == 1
            assert stats["total"] == 2


# ── API tests ────────────────────────────────────────────────────────

class TestJobsAPI:
    def test_list_empty(self, client, auth_header):
        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_stats_endpoint(self, client, auth_header):
        r = client.get("/jobs/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data

    def test_get_nonexistent(self, client, auth_header):
        r = client.get("/jobs/99999", headers=auth_header)
        assert r.status_code == 404

    def test_trigger_processing(self, client, auth_header):
        r = client.post("/jobs/process", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["processed"] == 0
