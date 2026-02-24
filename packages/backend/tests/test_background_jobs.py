"""Tests for background job retry and monitoring."""
import pytest
from datetime import datetime, timedelta

from app import create_app
from app.config import Settings
from app.extensions import db as _db
from app.models import (
    User, Bill, Reminder, ReminderDeliveryLog,
    JobExecutionLog, JobStatus, BillCadence, NotificationType,
)


@pytest.fixture
def app():
    settings = Settings(
        database_url="sqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        jwt_secret="test-secret",
        testing=True,
    )
    application = create_app(settings)
    return application


@pytest.fixture
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


class TestJobExecutionLog:
    def test_create_log_entry(self, app, db):
        with app.app_context():
            user = User(email="j@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.commit()
            log = JobExecutionLog(
                job_name="test_job",
                started_at=datetime.utcnow(),
                status=JobStatus.SUCCESS.value,
                records_processed=5,
                records_failed=0,
            )
            _db.session.add(log)
            _db.session.commit()
            assert log.id is not None
            assert log.job_name == "test_job"
            assert log.status == "SUCCESS"

    def test_log_status_values(self):
        assert JobStatus.SUCCESS.value == "SUCCESS"
        assert JobStatus.FAILED.value  == "FAILED"
        assert JobStatus.PARTIAL.value == "PARTIAL"
        assert JobStatus.RUNNING.value == "RUNNING"

    def test_log_query(self, app, db):
        with app.app_context():
            for i in range(3):
                _db.session.add(JobExecutionLog(
                    job_name=f"job_{i}",
                    started_at=datetime.utcnow() - timedelta(minutes=i),
                    status=JobStatus.SUCCESS.value,
                ))
            _db.session.commit()
            logs = _db.session.query(JobExecutionLog).order_by(
                JobExecutionLog.started_at.desc()
            ).all()
            assert len(logs) == 3
            assert logs[0].job_name == "job_0"


class TestSchedulerNotStartedInTest:
    def test_scheduler_not_active_in_test_mode(self, app):
        """In TESTING mode, scheduler should not be started."""
        with app.app_context():
            scheduler = app.extensions.get("scheduler")
            assert scheduler is None  # TESTING=True suppresses it


class TestJobsEndpoints:
    def test_status_requires_auth(self, client):
        resp = client.get("/jobs/status")
        assert resp.status_code in (401, 422)

    def test_status_endpoint_exists(self, client):
        resp = client.get("/jobs/status")
        assert resp.status_code != 404

    def test_history_requires_auth(self, client):
        resp = client.get("/jobs/history")
        assert resp.status_code in (401, 422)

    def test_history_endpoint_exists(self, client):
        resp = client.get("/jobs/history")
        assert resp.status_code != 404

    def test_trigger_requires_auth(self, client):
        resp = client.post("/jobs/send_pending_reminders/run")
        assert resp.status_code in (401, 422)


class TestRetryLogic:
    def test_max_retries_constant(self):
        from app.services.scheduler import _MAX_RETRIES
        assert _MAX_RETRIES >= 2
        assert _MAX_RETRIES <= 5

    def test_delivery_log_tracks_failures(self, app, db):
        with app.app_context():
            user = User(email="r@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.flush()
            r = Reminder(
                user_id=user.id, message="Bill due",
                send_at=datetime.utcnow() - timedelta(minutes=10),
                sent=False, channel="email",
            )
            _db.session.add(r)
            _db.session.flush()
            # Two failed attempts
            for _ in range(2):
                _db.session.add(ReminderDeliveryLog(
                    reminder_id=r.id, channel="email",
                    attempted_at=datetime.utcnow() - timedelta(minutes=5),
                    success=False, error_message="SMTP timeout",
                ))
            _db.session.commit()
            count = _db.session.query(ReminderDeliveryLog).filter(
                ReminderDeliveryLog.reminder_id == r.id,
                ReminderDeliveryLog.success == False,  # noqa: E712
            ).count()
            assert count == 2

    def test_sent_reminder_excluded_from_pending(self, app, db):
        with app.app_context():
            user = User(email="s@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.flush()
            sent_r = Reminder(
                user_id=user.id, message="Already sent",
                send_at=datetime.utcnow() - timedelta(hours=1),
                sent=True, channel="email",
            )
            unsent_r = Reminder(
                user_id=user.id, message="Not yet sent",
                send_at=datetime.utcnow() - timedelta(minutes=10),
                sent=False, channel="email",
            )
            _db.session.add_all([sent_r, unsent_r])
            _db.session.commit()
            pending = _db.session.query(Reminder).filter(
                Reminder.user_id == user.id,
                Reminder.sent == False,  # noqa: E712
                Reminder.send_at <= datetime.utcnow(),
            ).all()
            assert len(pending) == 1
            assert pending[0].message == "Not yet sent"
