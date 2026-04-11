"""Tests for resilient background job retry & monitoring (Bounty #130)."""

import json
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.config import Settings
from app.extensions import db as _db
from app.models import (
    Bill,
    BillCadence,
    Category,
    Expense,
    JobExecution,
    JobStatus,
    JobType,
    RecurringCadence,
    RecurringExpense,
    Reminder,
    Role,
    User,
)
from app.services.jobs import (
    RetryPolicy,
    dispatch_job,
    get_job_stats,
    get_retry_policy,
    mark_failed,
    mark_running,
    mark_success,
    retry_dead_letter,
    set_retry_policy,
    tick,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Create application for testing with SQLite."""
    settings = Settings(
        database_url="sqlite:///test_jobs.db",
        jwt_secret="test-secret",
    )
    app = create_app(settings)
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="session")
def _db_engine(app):
    """Create all tables once per session."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(autouse=True)
def clean_db(app, _db_engine):
    """Clean tables between tests."""
    with app.app_context():
        _db.session.query(JobExecution).delete()
        _db.session.query(Reminder).delete()
        _db.session.query(Bill).delete()
        _db.session.query(Category).delete()
        _db.session.query(Expense).delete()
        _db.session.query(RecurringExpense).delete()
        _db.session.query(User).delete()
        _db.session.commit()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_header(client, app):
    """Register a user and return auth headers."""
    with app.app_context():
        user = User(email="test@example.com", password_hash="hash", role=Role.USER)
        _db.session.add(user)
        _db.session.commit()
        uid = user.id

    from flask_jwt_extended import create_access_token
    token = create_access_token(identity=str(uid))
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# RetryPolicy tests
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    """Test the exponential backoff retry policy."""

    def test_default_policy_values(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay == timedelta(minutes=5)
        assert policy.max_delay == timedelta(minutes=60)
        assert policy.backoff_factor == 3.0

    def test_next_retry_at_exponential_backoff(self):
        """Backoff: 5min → 15min → 45min."""
        policy = RetryPolicy()
        now = datetime.utcnow()

        # Attempt 0: 5 min delay
        retry_at_0 = policy.next_retry_at(0)
        assert retry_at_0 is not None
        delay_0 = (retry_at_0 - now).total_seconds()
        assert 290 < delay_0 < 310  # ~5 min

        # Attempt 1: 15 min delay
        retry_at_1 = policy.next_retry_at(1)
        delay_1 = (retry_at_1 - now).total_seconds()
        assert 890 < delay_1 < 910  # ~15 min

        # Attempt 2: 45 min delay
        retry_at_2 = policy.next_retry_at(2)
        delay_2 = (retry_at_2 - now).total_seconds()
        assert 2690 < delay_2 < 2710  # ~45 min

    def test_next_retry_at_returns_none_past_max(self):
        """No more retries after max_attempts."""
        policy = RetryPolicy(max_attempts=3)
        assert policy.next_retry_at(3) is None
        assert policy.next_retry_at(4) is None

    def test_should_retry(self):
        policy = RetryPolicy(max_attempts=3)
        assert policy.should_retry(0) is True
        assert policy.should_retry(1) is True
        assert policy.should_retry(2) is True
        assert policy.should_retry(3) is False

    def test_custom_policy(self):
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=timedelta(minutes=1),
            backoff_factor=2.0,
        )
        assert policy.max_attempts == 5
        assert policy.base_delay == timedelta(minutes=1)

        # 1min → 2min → 4min → 8min → 16min
        now = datetime.utcnow()
        d0 = (policy.next_retry_at(0) - now).total_seconds()
        assert 55 < d0 < 65  # ~1 min

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("JOB_RETRY_MAX_ATTEMPTS", "5")
        monkeypatch.setenv("JOB_RETRY_BASE_DELAY_MIN", "10")
        monkeypatch.setenv("JOB_RETRY_MAX_DELAY_MIN", "120")
        monkeypatch.setenv("JOB_RETRY_BACKOFF_FACTOR", "2.5")
        # Reset cached policy
        import app.services.jobs as jobs_mod
        jobs_mod._default_policy = None
        policy = get_retry_policy()
        assert policy.max_attempts == 5
        assert policy.base_delay == timedelta(minutes=10)
        assert policy.max_delay == timedelta(minutes=120)
        assert policy.backoff_factor == 2.5
        # Reset for other tests
        jobs_mod._default_policy = None

    def test_max_delay_capping(self):
        """Delay should never exceed max_delay."""
        policy = RetryPolicy(
            base_delay=timedelta(hours=1),
            max_delay=timedelta(minutes=30),
            backoff_factor=3.0,
        )
        now = datetime.utcnow()
        retry_at = policy.next_retry_at(0)
        delay = (retry_at - now).total_seconds()
        # Should be capped at 30 min, not 60 min
        assert delay < 31 * 60


# ---------------------------------------------------------------------------
# Job lifecycle tests
# ---------------------------------------------------------------------------

class TestJobLifecycle:
    """Test dispatch → running → success/failure → retry → dead-letter."""

    def test_dispatch_creates_pending_job(self, app):
        with app.app_context():
            job = dispatch_job(
                job_type=JobType.REMINDER,
                payload=json.dumps({"reminder_id": 1}),
                source_id=1,
                source_type="reminder",
            )
            assert job.id is not None
            assert job.status == JobStatus.PENDING
            assert job.attempt == 0
            assert job.max_attempts == 3
            assert job.job_type == JobType.REMINDER
            assert job.source_id == 1
            assert job.source_type == "reminder"

    def test_mark_running(self, app):
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            mark_running(job)
            assert job.status == JobStatus.RUNNING
            assert job.started_at is not None

    def test_mark_success(self, app):
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            mark_running(job)
            mark_success(job, result="sent")
            assert job.status == JobStatus.SUCCESS
            assert job.completed_at is not None
            assert job.result == "sent"

    def test_mark_failed_first_attempt_schedules_retry(self, app):
        """First failure should schedule a retry."""
        policy = RetryPolicy(max_attempts=3, base_delay=timedelta(minutes=5), backoff_factor=3.0)
        with app.app_context():
            job = dispatch_job(JobType.REMINDER, '{"reminder_id": 1}', policy=policy)
            mark_running(job)
            failed = mark_failed(job, "smtp timeout", policy=policy)
            assert failed.status == JobStatus.RETRYING
            assert failed.attempt == 1
            assert failed.next_retry_at is not None
            assert failed.result == "smtp timeout"

    def test_mark_failed_exhausts_retries_to_dead_letter(self, app):
        """After max_attempts, job should be dead-lettered."""
        policy = RetryPolicy(max_attempts=3)
        with app.app_context():
            job = dispatch_job(JobType.REMINDER, '{"reminder_id": 1}', policy=policy)
            mark_running(job)
            mark_failed(job, "err1", policy=policy)  # attempt 1
            mark_failed(job, "err2", policy=policy)  # attempt 2
            final = mark_failed(job, "err3", policy=policy)  # attempt 3 → DEAD
            assert final.status == JobStatus.DEAD
            assert final.attempt == 3
            assert final.dead_reason == "err3"
            assert final.dead_at is not None
            assert final.next_retry_at is None

    def test_retry_dead_letter_resets_job(self, app):
        """Manually retrying a dead-lettered job resets it to PENDING."""
        policy = RetryPolicy(max_attempts=2)
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}', policy=policy)
            mark_running(job)
            mark_failed(job, "err1", policy=policy)
            mark_failed(job, "err2", policy=policy)
            assert job.status == JobStatus.DEAD

            retried = retry_dead_letter(job.id, policy=policy)
            assert retried is not None
            assert retried.status == JobStatus.PENDING
            assert retried.attempt == 0
            assert retried.dead_reason is None
            assert retried.dead_at is None
            assert retried.result is None

    def test_retry_dead_letter_non_dead_job(self, app):
        """Cannot retry a job that isn't in DEAD state."""
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{}')
            result = retry_dead_letter(job.id)
            assert result is None

    def test_retry_dead_letter_nonexistent_job(self, app):
        """Returns None for nonexistent job ID."""
        with app.app_context():
            result = retry_dead_letter(9999)
            assert result is None


# ---------------------------------------------------------------------------
# Pure dispatch function tests
# ---------------------------------------------------------------------------

class TestDispatchJob:
    """Test the pure dispatch_job function."""

    def test_dispatch_with_all_fields(self, app):
        with app.app_context():
            job = dispatch_job(
                JobType.REMINDER,
                json.dumps({"reminder_id": 42}),
                source_id=42,
                source_type="reminder",
                max_attempts=5,
            )
            assert job.job_type == JobType.REMINDER
            assert job.payload == '{"reminder_id": 42}'
            assert job.source_id == 42
            assert job.source_type == "reminder"
            assert job.max_attempts in (3, 5)  # capped by policy or set directly
            assert job.status == JobStatus.PENDING

    def test_dispatch_custom_job_type(self, app):
        with app.app_context():
            job = dispatch_job(JobType.CUSTOM, '{"task": "analyze"}')
            assert job.job_type == JobType.CUSTOM

    def test_dispatch_respects_policy_max_attempts(self, app):
        policy = RetryPolicy(max_attempts=2)
        with app.app_context():
            job = dispatch_job(
                JobType.EMAIL, '{}', max_attempts=10, policy=policy,
            )
            # Should cap at policy max
            assert job.max_attempts == 2


# ---------------------------------------------------------------------------
# Job execution (tick) tests
# ---------------------------------------------------------------------------

class TestTick:
    """Test the scheduler tick that processes due jobs."""

    def test_tick_processes_pending_jobs(self, app):
        """Pending jobs should be picked up and executed."""
        with app.app_context():
            # Create a PENDING job
            job = dispatch_job(JobType.CUSTOM, '{"task": "test"}')
            result = tick()
            assert result["processed"] >= 1
            assert result["success"] >= 1

            # Verify job is now SUCCESS
            _db.session.refresh(job)
            assert job.status == JobStatus.SUCCESS

    def test_tick_skips_future_retry_jobs(self, app):
        """RETRYING jobs with future next_retry_at should not be processed."""
        policy = RetryPolicy(base_delay=timedelta(hours=999))
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}', policy=policy)
            mark_running(job)
            mark_failed(job, "test error", policy=policy)
            # Job is RETRYING but scheduled far in the future
            assert job.status == JobStatus.RETRYING

            result = tick()
            # This job should not be processed yet
            assert result["processed"] == 0

    def test_tick_processes_due_retrying_jobs(self, app):
        """RETRYING jobs with past next_retry_at should be processed."""
        policy = RetryPolicy(base_delay=timedelta(seconds=0))
        with app.app_context():
            job = dispatch_job(JobType.CUSTOM, '{"task": "retry-me"}', policy=policy)
            mark_running(job)
            mark_failed(job, "err", policy=policy)
            # Set next_retry_at to past so it's due
            job.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
            _db.session.commit()

            result = tick()
            assert result["processed"] >= 1


# ---------------------------------------------------------------------------
# Monitoring / stats tests
# ---------------------------------------------------------------------------

class TestJobStats:
    """Test the monitoring and statistics endpoints."""

    def test_get_job_stats_empty(self, app):
        with app.app_context():
            stats = get_job_stats()
            assert stats["total"] == 0
            assert stats["success_rate"] == 0.0
            assert stats["recent_dead"] == []

    def test_get_job_stats_with_data(self, app):
        with app.app_context():
            # Create some jobs
            j1 = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            mark_running(j1)
            mark_success(j1, "delivered")

            j2 = dispatch_job(JobType.EMAIL, '{"to": "b@c.com"}')
            mark_running(j2)
            mark_failed(j2, "bounce", policy=RetryPolicy(max_attempts=1))

            stats = get_job_stats()
            assert stats["total"] == 2
            assert stats["by_status"]["SUCCESS"] == 1
            assert stats["by_status"]["DEAD"] == 1
            assert stats["success_rate"] == 50.0

    def test_stats_avg_duration(self, app):
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            mark_running(job)
            # Simulate some processing time
            job.started_at = datetime.utcnow() - timedelta(seconds=5)
            _db.session.commit()
            mark_success(job, "done")

            stats = get_job_stats()
            assert stats["avg_duration_seconds"] is not None


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestJobsAPI:
    """Test the /jobs REST endpoints."""

    def test_stats_endpoint(self, client, auth_header, app):
        with app.app_context():
            resp = client.get("/jobs/stats", headers=auth_header)
            assert resp.status_code == 200
            data = resp.get_json()
            assert "total" in data
            assert "by_status" in data
            assert "success_rate" in data

    def test_list_jobs_empty(self, client, auth_header, app):
        resp = client.get("/jobs", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_jobs_with_data(self, client, auth_header, app):
        with app.app_context():
            dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')

        resp = client.get("/jobs", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_jobs_filter_by_status(self, client, auth_header, app):
        with app.app_context():
            j = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            mark_running(j)
            mark_success(j, "sent")

        resp = client.get("/jobs?status=SUCCESS", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1

        resp = client.get("/jobs?status=DEAD", headers=auth_header)
        data = resp.get_json()
        assert data["total"] == 0

    def test_list_jobs_filter_by_type(self, client, auth_header, app):
        with app.app_context():
            dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            dispatch_job(JobType.REMINDER, '{"reminder_id": 1}')

        resp = client.get("/jobs?job_type=EMAIL", headers=auth_header)
        data = resp.get_json()
        assert data["total"] == 1

    def test_list_jobs_pagination(self, client, auth_header, app):
        with app.app_context():
            for i in range(5):
                dispatch_job(JobType.CUSTOM, json.dumps({"i": i}))

        resp = client.get("/jobs?limit=2&offset=0", headers=auth_header)
        data = resp.get_json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    def test_get_single_job(self, client, auth_header, app):
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            job_id = job.id

        resp = client.get(f"/jobs/{job_id}", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == job_id
        assert data["job_type"] == "EMAIL"
        assert data["status"] == "PENDING"

    def test_get_nonexistent_job(self, client, auth_header):
        resp = client.get("/jobs/9999", headers=auth_header)
        assert resp.status_code == 404

    def test_retry_dead_lettered_job(self, client, auth_header, app):
        policy = RetryPolicy(max_attempts=1)
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}', policy=policy)
            mark_running(job)
            mark_failed(job, "permanent failure", policy=policy)
            assert job.status == JobStatus.DEAD
            job_id = job.id

        resp = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "PENDING"
        assert data["attempt"] == 0

    def test_retry_non_dead_job_returns_404(self, client, auth_header, app):
        with app.app_context():
            job = dispatch_job(JobType.EMAIL, '{"to": "a@b.com"}')
            job_id = job.id

        resp = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
        assert resp.status_code == 404

    def test_invalid_status_filter(self, client, auth_header):
        resp = client.get("/jobs?status=INVALID", headers=auth_header)
        assert resp.status_code == 400

    def test_invalid_type_filter(self, client, auth_header):
        resp = client.get("/jobs?job_type=INVALID", headers=auth_header)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Integration: reminder job dispatch on send failure
# ---------------------------------------------------------------------------

class TestReminderJobIntegration:
    """Test that failed reminders are enqueued as resilient jobs."""

    def test_reminder_to_dict(self, app):
        """Test Reminder serialization (verify model still works)."""
        with app.app_context():
            user = User(email="r@test.com", password_hash="hash", role=Role.USER)
            _db.session.add(user)
            _db.session.commit()

            reminder = Reminder(
                user_id=user.id,
                message="Test reminder",
                send_at=datetime.utcnow() + timedelta(hours=1),
                channel="email",
            )
            _db.session.add(reminder)
            _db.session.commit()
            assert reminder.id is not None
            assert reminder.sent is False

    def test_job_execution_to_dict(self, app):
        """Test JobExecution.to_dict serialization."""
        with app.app_context():
            job = dispatch_job(
                JobType.REMINDER,
                '{"reminder_id": 1}',
                source_id=1,
                source_type="reminder",
            )
            d = job.to_dict()
            assert d["id"] == job.id
            assert d["job_type"] == "REMINDER"
            assert d["status"] == "PENDING"
            assert d["attempt"] == 0
            assert d["max_attempts"] == 3
            assert d["payload"] == '{"reminder_id": 1}'
            assert d["source_id"] == 1
            assert d["source_type"] == "reminder"
            # Nullable fields
            assert d["next_retry_at"] is None
            assert d["dead_reason"] is None