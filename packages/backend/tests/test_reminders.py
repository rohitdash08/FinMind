from datetime import date, datetime, timedelta
from unittest.mock import patch
import pytest

from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import User, Reminder


# Note: conftest.py provides client and auth_header fixtures


def _get_test_user_id(client, auth_header):
    """Extract user ID from the auth_header by decoding token or querying DB."""
    # The test user email is fixed in conftest: test@example.com
    with client.application.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        if user:
            return user.id
    # Fallback: decode token
    from flask_jwt_extended import decode_token
    token = auth_header["Authorization"].split()[1]
    claims = decode_token(token)
    return int(claims["sub"])


@pytest.fixture()
def admin_user(client, auth_header):
    """Promote the test user to admin and return auth_header."""
    uid = _get_test_user_id(client, auth_header)
    with client.application.app_context():
        user = db.session.get(User, uid)
        user.role = "ADMIN"
        db.session.commit()
    return auth_header


def test_retry_logic_increments_retry_count_and_schedules_backoff(client, auth_header):
    uid = _get_test_user_id(client, auth_header)
    with client.application.app_context():
        reminder = Reminder(
            user_id=uid,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="email",
            status="pending",
        )
        db.session.add(reminder)
        db.session.commit()
        reminder_id = reminder.id

    from app.services.reminders import dispatch_reminder

    # Patch the internal send to always fail
    with patch("app.services.reminders._send_reminder_internal", return_value=False):
        dispatch_reminder(reminder_id)

    with client.application.app_context():
        r = db.session.get(Reminder, reminder_id)
        assert r.retry_count == 1
        assert r.status == "retrying"
        assert r.last_retry_at is not None
        assert r.next_retry_at is not None
        assert r.failure_reason == "send_reminder failed"
        assert r.sent is False

        # Check backoff: next_retry_at should be ~5 minutes from last_retry_at
        delta = r.next_retry_at - r.last_retry_at
        assert 300 <= delta.total_seconds() <= 305  # 5 minutes buffer


def test_max_retries_exhausted_sets_failed_status(client, auth_header):
    uid = _get_test_user_id(client, auth_header)
    with client.application.app_context():
        reminder = Reminder(
            user_id=uid,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="email",
            status="pending",
        )
        db.session.add(reminder)
        db.session.commit()
        reminder_id = reminder.id

    from app.services.reminders import dispatch_reminder, MAX_RETRIES

    # Fail repeatedly
    with patch("app.services.reminders._send_reminder_internal", return_value=False):
        for _ in range(MAX_RETRIES + 1):
            dispatch_reminder(reminder_id)

    with client.application.app_context():
        r = db.session.get(Reminder, reminder_id)
        assert r.status == "failed"
        assert r.retry_count == MAX_RETRIES + 1
        assert r.next_retry_at is None
        assert r.sent is False


def test_success_on_retry_clears_fields(client, auth_header):
    uid = _get_test_user_id(client, auth_header)
    with client.application.app_context():
        reminder = Reminder(
            user_id=uid,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="email",
            status="pending",
        )
        db.session.add(reminder)
        db.session.commit()
        reminder_id = reminder.id

    from app.services.reminders import dispatch_reminder

    # First attempt fails
    with patch("app.services.reminders._send_reminder_internal", return_value=False):
        dispatch_reminder(reminder_id)

    with client.application.app_context():
        r = db.session.get(Reminder, reminder_id)
        assert r.status == "retrying"
        assert r.retry_count == 1

    # Second attempt succeeds
    with patch("app.services.reminders._send_reminder_internal", return_value=True):
        dispatch_reminder(reminder_id)

    with client.application.app_context():
        r = db.session.get(Reminder, reminder_id)
        assert r.sent is True
        assert r.status == "sent"
        assert r.retry_count == 0
        assert r.last_retry_at is None
        assert r.next_retry_at is None
        assert r.failure_reason is None


def test_admin_metrics_requires_admin(client, auth_header):
    # Regular user
    r = client.get("/admin/reminders/metrics", headers=auth_header)
    assert r.status_code == 403


def test_admin_metrics_returns_data(client, admin_user):
    r = client.get("/admin/reminders/metrics", headers=admin_user)
    assert r.status_code == 200
    data = r.get_json()
    assert "total" in data
    assert "by_status" in data
    assert "pending_retry" in data
    assert "avg_retries_for_failed" in data
    assert "recent_failures" in data
    assert isinstance(data["by_status"], dict)


def test_admin_failures_requires_admin(client, auth_header):
    r = client.get("/admin/reminders/failures", headers=auth_header)
    assert r.status_code == 403


def test_admin_failures_returns_list(client, admin_user):
    r = client.get("/admin/reminders/failures?limit=10", headers=admin_user)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    # Structure check if any failures exist
    for item in data:
        assert "id" in item
        assert "user_id" in item
        assert "message" in item
        assert "retry_count" in item
        assert "failure_reason" in item
