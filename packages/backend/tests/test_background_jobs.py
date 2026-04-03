"""Tests for Background Job Queue Architecture (issue #71)."""
import pytest
from datetime import datetime, timedelta
from app.services.background_jobs import (
    enqueue_job,
    process_job,
    cancel_job,
    get_job_stats,
    get_user_jobs,
    get_registered_job_types,
    register_job_handler,
    BackgroundJob,
    JobStatus,
    JobPriority,
)
from app.extensions import db

try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url("redis://localhost:6379/15")
    _r.ping()
    _redis_available = True
except Exception:
    _redis_available = False

requires_redis = pytest.mark.skipif(
    not _redis_available, reason="Redis not available"
)


# -----------------------------------------------------------------------
# Unit tests (no fixtures)
# -----------------------------------------------------------------------

class TestJobStatusEnum:
    def test_all_statuses_exist(self):
        statuses = {s.value for s in JobStatus}
        assert "pending" in statuses
        assert "running" in statuses
        assert "completed" in statuses
        assert "failed" in statuses
        assert "cancelled" in statuses

    def test_all_priorities_exist(self):
        priorities = {p.value for p in JobPriority}
        assert "low" in priorities
        assert "normal" in priorities
        assert "high" in priorities
        assert "critical" in priorities


class TestHandlerRegistry:
    def test_register_and_get_handler(self):
        @register_job_handler("test_handler_unit")
        def my_handler(payload, user_id=None):
            return {"done": True}

        types = get_registered_job_types()
        assert "test_handler_unit" in types

    def test_built_in_handlers_registered(self):
        types = get_registered_job_types()
        assert "expense_import" in types
        assert "ai_spending_analysis" in types
        assert "reminder_dispatch" in types
        assert "statement_normalization" in types

    def test_handler_receives_payload(self):
        results = {}

        @register_job_handler("test_payload_handler")
        def capture(payload, user_id=None):
            results["payload"] = payload
            results["user_id"] = user_id
            return {"ok": True}

        # We can call the handler directly (not through the job queue in unit tests)
        from app.services import background_jobs as bj
        handler = bj._JOB_HANDLERS["test_payload_handler"]
        result = handler({"key": "value"}, user_id=42)
        assert result == {"ok": True}
        assert results["payload"] == {"key": "value"}
        assert results["user_id"] == 42


# -----------------------------------------------------------------------
# Integration tests (need app_fixture + db)
# -----------------------------------------------------------------------

class TestJobLifecycle:
    def test_enqueue_creates_pending_job(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job(
                job_type="expense_import",
                payload={"rows": []},
                user_id=1,
            )
            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 0
            assert job.get_payload() == {"rows": []}

    def test_enqueue_custom_priority(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job(
                job_type="reminder_dispatch",
                payload={"reminder_ids": [1, 2]},
                user_id=1,
                priority=JobPriority.HIGH.value,
            )
            assert job.priority == JobPriority.HIGH.value

    def test_process_job_success(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job(
                job_type="expense_import",
                payload={"rows": [{"amount": 100, "date": "2026-01-01"}]},
                user_id=1,
            )
            success = process_job(job)
            assert success is True
            assert job.status == JobStatus.COMPLETED.value
            assert job.completed_at is not None
            result = job.get_result()
            assert result is not None
            assert result["processed"] == 1

    def test_process_job_unknown_type_fails(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job(
                job_type="nonexistent_job_type_xyz",
                payload={},
                user_id=1,
            )
            success = process_job(job)
            assert success is False
            assert job.status == JobStatus.FAILED.value
            assert "No handler registered" in job.error_message

    def test_process_job_retries_on_error(self, app_fixture):
        with app_fixture.app_context():
            call_count = [0]

            @register_job_handler("flaky_job")
            def flaky(payload, user_id=None):
                call_count[0] += 1
                raise ValueError("Temporary error")

            job = enqueue_job(
                job_type="flaky_job",
                payload={},
                user_id=1,
                max_retries=2,
            )
            # First failure
            process_job(job)
            assert job.status == JobStatus.PENDING.value  # queued for retry
            assert job.retry_count == 1
            assert job.next_retry_at is not None

    def test_process_job_fails_after_max_retries(self, app_fixture):
        with app_fixture.app_context():
            @register_job_handler("always_fail_job")
            def always_fail(payload, user_id=None):
                raise RuntimeError("Permanent error")

            job = enqueue_job(
                job_type="always_fail_job",
                payload={},
                user_id=1,
                max_retries=0,  # no retries
            )
            process_job(job)
            assert job.status == JobStatus.FAILED.value
            assert job.retry_count == 1
            assert "Permanent error" in job.error_message

    def test_cancel_pending_job(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("expense_import", {}, user_id=1)
            cancelled = cancel_job(job.id, user_id=1)
            assert cancelled is not None
            assert cancelled.status == JobStatus.CANCELLED.value

    def test_cancel_wrong_user_fails(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("expense_import", {}, user_id=1)
            result = cancel_job(job.id, user_id=999)
            assert result is None  # different user can't cancel

    def test_cancel_running_job_not_allowed(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("expense_import", {}, user_id=1)
            job.status = JobStatus.RUNNING.value
            db.session.commit()
            result = cancel_job(job.id, user_id=1)
            assert result is None


class TestJobStats:
    def test_stats_by_status(self, app_fixture):
        with app_fixture.app_context():
            enqueue_job("expense_import", {}, user_id=2)
            enqueue_job("reminder_dispatch", {"reminder_ids": []}, user_id=2)
            stats = get_job_stats(user_id=2)
            assert stats["pending"] >= 2
            assert stats["total"] >= 2
            assert "registered_job_types" in stats

    def test_get_user_jobs_paged(self, app_fixture):
        with app_fixture.app_context():
            for i in range(5):
                enqueue_job("ai_spending_analysis", {"period": f"month_{i}"}, user_id=3)
            result = get_user_jobs(user_id=3, limit=3, offset=0)
            assert len(result["jobs"]) == 3
            assert result["total"] >= 5

    def test_get_user_jobs_filter_by_status(self, app_fixture):
        with app_fixture.app_context():
            job = enqueue_job("expense_import", {}, user_id=4)
            cancel_job(job.id, user_id=4)
            result = get_user_jobs(user_id=4, status=JobStatus.CANCELLED.value)
            assert result["total"] >= 1
            for j in result["jobs"]:
                assert j["status"] == JobStatus.CANCELLED.value


# -----------------------------------------------------------------------
# API integration tests (require Redis for JWT)
# -----------------------------------------------------------------------

@requires_redis
class TestBackgroundJobsAPI:
    def test_create_job(self, client, auth_header):
        resp = client.post("/jobs", json={
            "job_type": "expense_import",
            "payload": {"rows": []},
            "priority": "normal",
        }, headers=auth_header)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "pending"
        assert data["job_type"] == "expense_import"

    def test_create_job_invalid_type(self, client, auth_header):
        resp = client.post("/jobs", json={
            "job_type": "",
        }, headers=auth_header)
        assert resp.status_code == 400

    def test_create_job_invalid_priority(self, client, auth_header):
        resp = client.post("/jobs", json={
            "job_type": "expense_import",
            "priority": "super_urgent",
        }, headers=auth_header)
        assert resp.status_code == 400

    def test_list_jobs(self, client, auth_header):
        client.post("/jobs", json={"job_type": "reminder_dispatch", "payload": {"reminder_ids": []}}, headers=auth_header)
        resp = client.get("/jobs", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "jobs" in data
        assert "total" in data

    def test_get_job_not_found(self, client, auth_header):
        resp = client.get("/jobs/999999", headers=auth_header)
        assert resp.status_code == 404

    def test_job_stats(self, client, auth_header):
        resp = client.get("/jobs/stats", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "pending" in data
        assert "total" in data

    def test_list_job_types_public(self, client):
        resp = client.get("/jobs/types")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "job_types" in data
        assert "expense_import" in data["job_types"]

    def test_cancel_job(self, client, auth_header):
        create_resp = client.post("/jobs", json={
            "job_type": "ai_spending_analysis",
            "payload": {"period": "last_30_days"},
        }, headers=auth_header)
        job_id = create_resp.get_json()["id"]
        cancel_resp = client.post(f"/jobs/{job_id}/cancel", headers=auth_header)
        assert cancel_resp.status_code == 200
        assert cancel_resp.get_json()["status"] == "cancelled"