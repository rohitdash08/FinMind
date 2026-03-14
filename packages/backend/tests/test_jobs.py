"""
Tests for background job retry logic and monitoring endpoints.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Reminder
from app.extensions import db
from app.services.scheduler import process_due_reminders, MAX_RETRIES, _backoff_delta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reminder(app_fixture, *, send_at_offset_minutes=-2, **kwargs):
    """Create a reminder via the DB directly for unit-level tests."""
    with app_fixture.app_context():
        r = Reminder(
            user_id=1,
            message="Test reminder",
            send_at=datetime.utcnow() + timedelta(minutes=send_at_offset_minutes),
            channel="email",
            **kwargs,
        )
        db.session.add(r)
        db.session.commit()
        return r.id


def _get_reminder(app_fixture, reminder_id):
    with app_fixture.app_context():
        return db.session.get(Reminder, reminder_id)


def _register_user(client):
    client.post("/auth/register", json={"email": "job@test.com", "password": "pass1234"})
    r = client.post("/auth/login", json={"email": "job@test.com", "password": "pass1234"})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


# ---------------------------------------------------------------------------
# Retry logic unit tests
# ---------------------------------------------------------------------------

class TestBackoffDelta:
    def test_first_retry_is_5_minutes(self):
        assert _backoff_delta(0) == timedelta(minutes=5)

    def test_second_retry_is_15_minutes(self):
        assert _backoff_delta(1) == timedelta(minutes=15)

    def test_third_retry_is_45_minutes(self):
        assert _backoff_delta(2) == timedelta(minutes=45)

    def test_beyond_max_clamps_to_last_bucket(self):
        assert _backoff_delta(99) == timedelta(minutes=45)


class TestProcessDueReminders:
    def test_successful_send_marks_reminder_sent(self, app_fixture):
        rid = _make_reminder(app_fixture)
        with patch("app.services.scheduler.send_reminder", return_value=True):
            result = process_due_reminders(app=app_fixture)
        assert result["sent"] == 1
        assert result["total_processed"] == 1
        r = _get_reminder(app_fixture, rid)
        assert r.sent is True
        assert r.retry_count == 0

    def test_failed_send_increments_retry_and_sets_next_retry(self, app_fixture):
        rid = _make_reminder(app_fixture)
        with patch("app.services.scheduler.send_reminder", return_value=False):
            result = process_due_reminders(app=app_fixture)
        assert result["retried"] == 1
        assert result["sent"] == 0
        r = _get_reminder(app_fixture, rid)
        assert r.sent is False
        assert r.retry_count == 1
        assert r.next_retry_at is not None
        assert r.failed is False
        assert r.last_error is not None

    def test_reminder_not_retried_before_next_retry_at(self, app_fixture):
        # Create a reminder that already failed once, next_retry_at in the future
        rid = _make_reminder(
            app_fixture,
            retry_count=1,
            next_retry_at=datetime.utcnow() + timedelta(hours=1),
            last_error="previous failure",
        )
        with patch("app.services.scheduler.send_reminder", return_value=True) as mock_send:
            process_due_reminders(app=app_fixture)
        mock_send.assert_not_called()

    def test_reminder_retried_after_next_retry_at_passes(self, app_fixture):
        rid = _make_reminder(
            app_fixture,
            retry_count=1,
            next_retry_at=datetime.utcnow() - timedelta(minutes=1),
            last_error="previous failure",
        )
        with patch("app.services.scheduler.send_reminder", return_value=True):
            result = process_due_reminders(app=app_fixture)
        assert result["sent"] == 1
        r = _get_reminder(app_fixture, rid)
        assert r.sent is True

    def test_permanently_failed_after_max_retries(self, app_fixture):
        rid = _make_reminder(
            app_fixture,
            retry_count=MAX_RETRIES - 1,
            next_retry_at=datetime.utcnow() - timedelta(minutes=1),
        )
        with patch("app.services.scheduler.send_reminder", return_value=False):
            result = process_due_reminders(app=app_fixture)
        assert result["permanently_failed"] == 1
        r = _get_reminder(app_fixture, rid)
        assert r.failed is True
        assert r.retry_count == MAX_RETRIES

    def test_failed_reminder_not_reprocessed(self, app_fixture):
        rid = _make_reminder(app_fixture, failed=True)
        with patch("app.services.scheduler.send_reminder") as mock_send:
            process_due_reminders(app=app_fixture)
        mock_send.assert_not_called()

    def test_future_reminder_not_processed(self, app_fixture):
        rid = _make_reminder(app_fixture, send_at_offset_minutes=60)
        with patch("app.services.scheduler.send_reminder") as mock_send:
            process_due_reminders(app=app_fixture)
        mock_send.assert_not_called()

    def test_sent_reminder_not_reprocessed(self, app_fixture):
        rid = _make_reminder(app_fixture, sent=True)
        with patch("app.services.scheduler.send_reminder") as mock_send:
            process_due_reminders(app=app_fixture)
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Monitoring endpoint tests
# ---------------------------------------------------------------------------

class TestJobEndpoints:
    def test_scheduler_status_returns_not_running_in_test_mode(self, client, auth_header):
        # Scheduler is not started in TESTING=True mode
        r = client.get("/jobs/status", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["running"] is False
        assert data["jobs"] == []

    def test_reminder_stats_empty(self, client, auth_header):
        r = client.get("/jobs/reminders/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0
        assert data["sent"] == 0
        assert data["pending"] == 0
        assert data["permanently_failed"] == 0

    def test_reminder_stats_reflect_state(self, client, auth_header, app_fixture):
        # Create reminders via API
        bill_r = client.post(
            "/bills",
            json={
                "name": "Netflix",
                "amount": 15.0,
                "next_due_date": "2026-04-01",
                "cadence": "MONTHLY",
            },
            headers=auth_header,
        )
        bill_id = bill_r.get_json()["id"]
        client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)

        r = client.get("/jobs/reminders/stats", headers=auth_header)
        data = r.get_json()
        assert data["total"] > 0
        assert data["pending"] > 0

    def test_manual_trigger_endpoint(self, client, auth_header):
        with patch("app.routes.jobs.process_due_reminders", return_value={"sent": 0, "retried": 0, "permanently_failed": 0, "total_processed": 0}) as mock:
            r = client.post("/jobs/reminders/run", headers=auth_header)
        assert r.status_code == 200
        mock.assert_called_once()

    def test_endpoints_require_auth(self, client):
        assert client.get("/jobs/status").status_code == 401
        assert client.get("/jobs/reminders/stats").status_code == 401
        assert client.post("/jobs/reminders/run").status_code == 401
