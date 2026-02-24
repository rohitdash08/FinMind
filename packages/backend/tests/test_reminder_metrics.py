"""Tests for reminder reliability tracking and delivery metrics."""
import pytest
from datetime import datetime, timedelta
from app.extensions import db as _db
from app.models import User, Reminder, ReminderDeliveryLog
from app.services.reminder_metrics import get_reminder_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db_session, email="test@x.com"):
    u = User(email=email, password_hash="x", preferred_currency="INR")
    db_session.add(u)
    db_session.flush()
    return u


def _make_reminder(db_session, user_id, channel="email", sent=False, offset_hours=-1):
    r = Reminder(
        user_id=user_id,
        message="Test reminder",
        send_at=datetime.utcnow() + timedelta(hours=offset_hours),
        sent=sent,
        channel=channel,
    )
    db_session.add(r)
    db_session.flush()
    return r


def _make_log(db_session, reminder_id, channel="email", success=True, hours_ago=1, latency=30):
    log = ReminderDeliveryLog(
        reminder_id=reminder_id,
        channel=channel,
        attempted_at=datetime.utcnow() - timedelta(hours=hours_ago),
        success=success,
        error_message=None if success else "SMTP connection failed",
        latency_seconds=latency if success else None,
    )
    db_session.add(log)
    return log


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------

class TestGetReminderMetrics:
    def test_empty_returns_zeros(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            assert result["total_attempts"] == 0
            assert result["success_rate"] == 0.0

    def test_counts_successes_and_failures(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "counts@x.com")
            r = _make_reminder(_db.session, user.id)
            _make_log(_db.session, r.id, success=True)
            _make_log(_db.session, r.id, success=True)
            _make_log(_db.session, r.id, success=False)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            assert result["total_sent"] == 2
            assert result["total_failed"] == 1
            assert result["success_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_by_channel_breakdown(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "chan@x.com")
            r_email = _make_reminder(_db.session, user.id, channel="email")
            r_wa = _make_reminder(_db.session, user.id, channel="whatsapp")
            _make_log(_db.session, r_email.id, channel="email", success=True)
            _make_log(_db.session, r_wa.id, channel="whatsapp", success=False)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            assert "email" in result["by_channel"]
            assert "whatsapp" in result["by_channel"]
            assert result["by_channel"]["email"]["sent"] == 1
            assert result["by_channel"]["whatsapp"]["failed"] == 1

    def test_avg_latency_calculated(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "lat@x.com")
            r = _make_reminder(_db.session, user.id)
            _make_log(_db.session, r.id, success=True, latency=60)
            _make_log(_db.session, r.id, success=True, latency=120)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            assert result["avg_latency_seconds"] == pytest.approx(90.0)

    def test_recent_failures_populated(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "fail@x.com")
            r = _make_reminder(_db.session, user.id)
            for i in range(3):
                _make_log(_db.session, r.id, success=False, hours_ago=i + 1)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            assert len(result["recent_failures"]) == 3
            assert all("reminder_id" in f for f in result["recent_failures"])
            assert all("error_message" in f for f in result["recent_failures"])

    def test_pending_reminders_counted(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "pend@x.com")
            _make_reminder(_db.session, user.id, sent=False, offset_hours=1)
            _make_reminder(_db.session, user.id, sent=False, offset_hours=2)
            _make_reminder(_db.session, user.id, sent=True, offset_hours=-1)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            assert result["pending_reminders"] == 2

    def test_response_shape(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "shape@x.com")
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session)
            for key in [
                "period_days",
                "total_reminders_scheduled",
                "total_attempts",
                "total_sent",
                "total_failed",
                "success_rate",
                "by_channel",
                "avg_latency_seconds",
                "recent_failures",
                "pending_reminders",
            ]:
                assert key in result

    def test_days_period_filter(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user(_db.session, "filter@x.com")
            r = _make_reminder(_db.session, user.id)
            # Log from 60 days ago — should NOT appear in 30-day window
            old_log = ReminderDeliveryLog(
                reminder_id=r.id,
                channel="email",
                attempted_at=datetime.utcnow() - timedelta(days=60),
                success=True,
                latency_seconds=30,
            )
            _db.session.add(old_log)
            # Recent log — should appear
            _make_log(_db.session, r.id, success=True, hours_ago=1)
            _db.session.commit()
            result = get_reminder_metrics(user.id, _db.session, days=30)
            assert result["total_attempts"] == 1  # only the recent one


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    def test_requires_auth(self, client):
        resp = client.get("/reminders/metrics")
        assert resp.status_code in (401, 422)

    def test_endpoint_exists(self, client):
        resp = client.get("/reminders/metrics")
        assert resp.status_code != 404

    def test_days_param_accepted(self, client):
        resp = client.get("/reminders/metrics?days=7")
        assert resp.status_code in (200, 401, 422)

    # NOTE: tests below require Redis (for JWT refresh token storage via auth_header).
    # They are marked xfail in environments without Redis, matching the existing test
    # suite behaviour (see test_reminders.py — same pattern).
    @pytest.mark.xfail(reason="requires Redis for auth_header fixture", strict=False)
    def test_authenticated_returns_200(self, client, auth_header):
        resp = client.get("/reminders/metrics", headers=auth_header)
        assert resp.status_code == 200

    @pytest.mark.xfail(reason="requires Redis for auth_header fixture", strict=False)
    def test_authenticated_returns_valid_shape(self, client, auth_header):
        resp = client.get("/reminders/metrics", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["period_days"], int)
        assert isinstance(data["success_rate"], float)
        assert isinstance(data["by_channel"], dict)
        assert isinstance(data["recent_failures"], list)
        assert isinstance(data["pending_reminders"], int)

    @pytest.mark.xfail(reason="requires Redis for auth_header fixture", strict=False)
    def test_days_param_changes_period(self, client, auth_header):
        resp = client.get("/reminders/metrics?days=7", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["period_days"] == 7
