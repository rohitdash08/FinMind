"""Tests for notification priority and grouping system."""
import pytest
from datetime import datetime, timedelta, date

from app import create_app
from app.config import Settings
from app.extensions import db as _db
from app.models import (
    User, Bill, Reminder, BillCadence,
    NotificationPriority, NotificationType,
)
from app.services.notification_grouping import auto_priority, get_grouped_notifications


@pytest.fixture
def app():
    settings = Settings(
        database_url="sqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        jwt_secret="test-secret",
    )
    application = create_app(settings)
    application.config["TESTING"] = True
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


def _make_user(email="u@x.com"):
    return User(email=email, password_hash="x", preferred_currency="INR")


def _make_bill(user_id, days_until_due=5, name="Electric"):
    return Bill(
        user_id=user_id, name=name, amount=500,
        currency="INR",
        next_due_date=date.today() + timedelta(days=days_until_due),
        cadence=BillCadence.MONTHLY,
    )


def _make_reminder(user_id, bill_id=None, priority="NORMAL",
                   ntype="CUSTOM", hours_from_now=1, sent=False):
    return Reminder(
        user_id=user_id,
        bill_id=bill_id,
        message="Test notification",
        send_at=datetime.utcnow() + timedelta(hours=hours_from_now),
        sent=sent,
        channel="email",
        priority=priority,
        notification_type=ntype,
    )


class TestAutoPriority:
    def test_urgent_for_bill_due_today(self, app, db):
        with app.app_context():
            user = _make_user("ap1@x.com")
            _db.session.add(user)
            _db.session.flush()
            bill = _make_bill(user.id, days_until_due=0)
            _db.session.add(bill)
            _db.session.flush()
            r = _make_reminder(user.id, bill_id=bill.id, ntype="BILL_REMINDER")
            _db.session.add(r)
            _db.session.commit()
            prio = auto_priority(r, _db.session)
            assert prio == NotificationPriority.URGENT.value

    def test_high_for_bill_due_in_2_days(self, app, db):
        with app.app_context():
            user = _make_user("ap2@x.com")
            _db.session.add(user)
            _db.session.flush()
            bill = _make_bill(user.id, days_until_due=2)
            _db.session.add(bill)
            _db.session.flush()
            r = _make_reminder(user.id, bill_id=bill.id, ntype="BILL_REMINDER")
            _db.session.add(r)
            _db.session.commit()
            prio = auto_priority(r, _db.session)
            assert prio == NotificationPriority.HIGH.value

    def test_low_for_bill_due_in_14_days(self, app, db):
        with app.app_context():
            user = _make_user("ap3@x.com")
            _db.session.add(user)
            _db.session.flush()
            bill = _make_bill(user.id, days_until_due=14)
            _db.session.add(bill)
            _db.session.flush()
            r = _make_reminder(user.id, bill_id=bill.id, ntype="BILL_REMINDER")
            _db.session.add(r)
            _db.session.commit()
            prio = auto_priority(r, _db.session)
            assert prio == NotificationPriority.LOW.value

    def test_normal_for_custom_notification(self, app, db):
        with app.app_context():
            user = _make_user("ap4@x.com")
            _db.session.add(user)
            _db.session.flush()
            r = _make_reminder(user.id, ntype="CUSTOM")
            _db.session.add(r)
            _db.session.commit()
            prio = auto_priority(r, _db.session)
            assert prio == NotificationPriority.NORMAL.value


class TestGetGroupedNotifications:
    def _seed(self, app, db, email="g@x.com"):
        with app.app_context():
            user = _make_user(email)
            _db.session.add(user)
            _db.session.flush()
            r_urgent = _make_reminder(user.id, priority="URGENT", ntype="BILL_REMINDER")
            r_high   = _make_reminder(user.id, priority="HIGH",   ntype="BILL_REMINDER")
            r_normal = _make_reminder(user.id, priority="NORMAL", ntype="CUSTOM")
            r_sent   = _make_reminder(user.id, priority="NORMAL", ntype="CUSTOM", sent=True)
            _db.session.add_all([r_urgent, r_high, r_normal, r_sent])
            _db.session.commit()
            return user.id

    def test_excludes_sent_by_default(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = get_grouped_notifications(uid, _db.session, include_sent=False)
            assert result["total"] == 3  # sent one excluded

    def test_includes_sent_when_flagged(self, app, db):
        uid = self._seed(app, db, email="g2@x.com")
        with app.app_context():
            result = get_grouped_notifications(uid, _db.session, include_sent=True)
            assert result["total"] == 4

    def test_urgent_bucket_populated(self, app, db):
        uid = self._seed(app, db, email="g3@x.com")
        with app.app_context():
            result = get_grouped_notifications(uid, _db.session)
            assert result["by_priority"]["URGENT"]["count"] == 1

    def test_by_type_buckets_present(self, app, db):
        uid = self._seed(app, db, email="g4@x.com")
        with app.app_context():
            result = get_grouped_notifications(uid, _db.session)
            assert "BILL_REMINDER" in result["by_type"]
            assert "CUSTOM" in result["by_type"]

    def test_summary_keys_present(self, app, db):
        uid = self._seed(app, db, email="g5@x.com")
        with app.app_context():
            result = get_grouped_notifications(uid, _db.session)
            for k in ["urgent_count", "overdue_count", "upcoming_24h"]:
                assert k in result["summary"]

    def test_empty_user_returns_zero(self, app, db):
        with app.app_context():
            _db.create_all()
            user = _make_user("empty@x.com")
            _db.session.add(user)
            _db.session.commit()
            result = get_grouped_notifications(user.id, _db.session)
            assert result["total"] == 0
            assert result["summary"]["urgent_count"] == 0


class TestNotificationEndpoints:
    def test_grouped_requires_auth(self, client):
        resp = client.get("/notifications/grouped")
        assert resp.status_code in (401, 422)

    def test_grouped_endpoint_exists(self, client):
        resp = client.get("/notifications/grouped")
        assert resp.status_code != 404

    def test_set_priority_requires_auth(self, client):
        resp = client.post("/notifications/1/priority", json={"priority": "HIGH"})
        assert resp.status_code in (401, 404, 422)

    def test_bulk_prioritise_requires_auth(self, client):
        resp = client.post("/notifications/bulk-prioritise")
        assert resp.status_code in (401, 422)
