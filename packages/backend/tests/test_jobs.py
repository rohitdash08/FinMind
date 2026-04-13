from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import (
    BackgroundJob,
    JobExecutionLog,
    JobStatus,
    Reminder,
    User,
    Role,
)
from app.services.jobs import (
    create_job,
    execute_job,
    register_handler,
    retry_failed_job,
    run_due_jobs,
    BACKOFF_BASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_admin(app_fixture, client):
    """Register a user and promote to ADMIN, return auth header."""
    email = "admin@example.com"
    password = "admin1234"
    with patch("app.routes.auth.redis_client", MagicMock()):
        client.post("/auth/register", json={"email": email, "password": password})
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            user.role = Role.ADMIN.value
            db.session.commit()
        r = client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


# ---------------------------------------------------------------------------
# Unit tests — job execution engine
# ---------------------------------------------------------------------------

class TestJobExecution:
    def test_create_job(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("test_type", payload={"key": "value"})
            assert job.id is not None
            assert job.status == JobStatus.PENDING.value
            assert job.payload == {"key": "value"}
            assert job.retry_count == 0
            assert job.max_retries == 3

    def test_execute_job_success(self, app_fixture):
        @register_handler("success_job")
        def _handler(payload):
            return {"result": "ok"}

        with app_fixture.app_context():
            job = create_job("success_job", payload={})
            result = execute_job(job)
            assert result.status == JobStatus.COMPLETED.value
            assert result.result == {"result": "ok"}
            assert result.last_error is None

            logs = db.session.query(JobExecutionLog).filter_by(job_id=job.id).all()
            assert len(logs) == 1
            assert logs[0].status == JobStatus.COMPLETED.value
            assert logs[0].attempt == 1

    def test_execute_job_failure_with_retry(self, app_fixture):
        call_count = 0

        @register_handler("fail_once_job")
        def _handler(payload):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise RuntimeError("temporary failure")
            return {"done": True}

        with app_fixture.app_context():
            job = create_job("fail_once_job", payload={})

            # First attempt fails
            execute_job(job)
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 1
            assert job.next_retry_at is not None
            assert "temporary failure" in job.last_error

            logs = db.session.query(JobExecutionLog).filter_by(job_id=job.id).all()
            assert len(logs) == 1
            assert logs[0].status == JobStatus.FAILED.value

            # Second attempt succeeds
            job.next_retry_at = None  # allow immediate retry
            db.session.commit()
            execute_job(job)
            assert job.status == JobStatus.COMPLETED.value
            assert job.retry_count == 1  # stays at 1 from failure

    def test_execute_job_permanent_failure(self, app_fixture):
        @register_handler("always_fail_job")
        def _handler(payload):
            raise RuntimeError("permanent problem")

        with app_fixture.app_context():
            job = create_job("always_fail_job", payload={}, max_retries=2)

            # First attempt
            execute_job(job)
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 1

            # Second attempt — should be permanently failed
            job.next_retry_at = None
            db.session.commit()
            execute_job(job)
            assert job.status == JobStatus.FAILED.value
            assert job.retry_count == 2
            assert job.next_retry_at is None

    def test_exponential_backoff_schedule(self, app_fixture):
        @register_handler("backoff_test")
        def _handler(payload):
            raise RuntimeError("fail")

        with app_fixture.app_context():
            job = create_job("backoff_test", payload={}, max_retries=5)

            execute_job(job)
            # After attempt 1: delay = 5^1 = 5s
            assert job.next_retry_at is not None
            delay1 = (job.next_retry_at - job.updated_at).total_seconds()
            assert abs(delay1 - BACKOFF_BASE ** 1) < 2

    def test_no_handler_marks_failed(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("nonexistent_handler", payload={})
            execute_job(job)
            assert job.status == JobStatus.FAILED.value
            assert "No handler" in job.last_error

    def test_run_due_jobs(self, app_fixture):
        @register_handler("due_job")
        def _handler(payload):
            return {"ok": True}

        with app_fixture.app_context():
            # Job with no next_retry_at (first attempt)
            j1 = create_job("due_job", payload={})

            # Job with future retry — should NOT be picked up
            j2 = create_job("due_job", payload={})
            j2.next_retry_at = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()

            results = run_due_jobs()
            ids = [j.id for j in results]
            assert j1.id in ids
            assert j2.id not in ids

    def test_retry_failed_job(self, app_fixture):
        @register_handler("retry_target")
        def _handler(payload):
            return {"retried": True}

        with app_fixture.app_context():
            job = create_job("retry_target", payload={})
            job.status = JobStatus.FAILED.value
            job.retry_count = 3
            db.session.commit()

            result = retry_failed_job(job.id)
            assert result.status == JobStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# API tests — admin endpoints
# ---------------------------------------------------------------------------

class TestAdminJobsAPI:
    def test_list_jobs_requires_admin(self, app_fixture, client):
        """Non-admin user should receive 403."""
        email = "regular@example.com"
        password = "regular1234"
        with patch("app.routes.auth.redis_client", MagicMock()):
            client.post("/auth/register", json={"email": email, "password": password})
            r = client.post("/auth/login", json={"email": email, "password": password})
        token = r.get_json()["access_token"]
        header = {"Authorization": f"Bearer {token}"}
        r = client.get("/admin/jobs", headers=header)
        assert r.status_code == 403

    def test_list_jobs_as_admin(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)
        with app_fixture.app_context():
            create_job("test_list", payload={"n": 1})
            create_job("test_list", payload={"n": 2})

        r = client.get("/admin/jobs", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 2
        assert len(data["jobs"]) >= 2

    def test_list_jobs_filter_by_status(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)
        with app_fixture.app_context():
            j = create_job("filter_test", payload={})
            j.status = JobStatus.COMPLETED.value
            db.session.commit()

        r = client.get("/admin/jobs?status=completed", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        statuses = [j["status"] for j in data["jobs"]]
        assert all(s == "completed" for s in statuses)

    def test_list_jobs_pagination(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)
        with app_fixture.app_context():
            for i in range(5):
                create_job("page_test", payload={"i": i})

        r = client.get("/admin/jobs?page=1&per_page=2", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["jobs"]) == 2
        assert data["per_page"] == 2

    def test_get_job_detail(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)

        @register_handler("detail_test")
        def _handler(payload):
            return {"ok": True}

        with app_fixture.app_context():
            job = create_job("detail_test", payload={"x": 1})
            execute_job(job)
            job_id = job.id

        r = client.get(f"/admin/jobs/{job_id}", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["job"]["id"] == job_id
        assert data["job"]["status"] == "completed"
        assert len(data["execution_history"]) == 1

    def test_get_job_not_found(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)
        r = client.get("/admin/jobs/99999", headers=admin_header)
        assert r.status_code == 404

    def test_retry_job_endpoint(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)

        @register_handler("retry_api_test")
        def _handler(payload):
            return {"retried": True}

        with app_fixture.app_context():
            job = create_job("retry_api_test", payload={})
            job.status = JobStatus.FAILED.value
            job.retry_count = 3
            db.session.commit()
            job_id = job.id

        r = client.post(f"/admin/jobs/{job_id}/retry", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["job"]["status"] == "completed"

    def test_retry_non_failed_job_rejected(self, app_fixture, client):
        admin_header = _make_admin(app_fixture, client)
        with app_fixture.app_context():
            job = create_job("nonfailed_test", payload={})
            job_id = job.id

        r = client.post(f"/admin/jobs/{job_id}/retry", headers=admin_header)
        assert r.status_code == 400
        assert "only failed" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Integration test — reminder job handler
# ---------------------------------------------------------------------------

class TestReminderJobIntegration:
    def test_send_reminder_via_job_framework(self, app_fixture):
        with app_fixture.app_context():
            from app.models import Reminder
            from app.services.jobs import create_job, execute_job

            r = Reminder(
                user_id=1,
                message="Test reminder",
                send_at=datetime.utcnow(),
                channel="email",
            )
            db.session.add(r)
            db.session.commit()
            reminder_id = r.id

            job = create_job(
                "send_reminder", payload={"reminder_id": reminder_id}
            )
            with patch("app.services.reminder_jobs.send_reminder", return_value=True):
                execute_job(job)

            assert job.status == JobStatus.COMPLETED.value
            updated = db.session.get(Reminder, reminder_id)
            assert updated.sent is True

    def test_send_reminder_failure_triggers_retry(self, app_fixture):
        with app_fixture.app_context():
            from app.models import Reminder
            from app.services.jobs import create_job, execute_job

            r = Reminder(
                user_id=1,
                message="Retry test reminder",
                send_at=datetime.utcnow(),
                channel="email",
            )
            db.session.add(r)
            db.session.commit()
            reminder_id = r.id

            job = create_job(
                "send_reminder", payload={"reminder_id": reminder_id}
            )
            with patch(
                "app.services.reminder_jobs.send_reminder", return_value=False
            ):
                execute_job(job)

            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 1
            assert job.next_retry_at is not None
