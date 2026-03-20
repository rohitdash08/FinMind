"""Tests for resilient background job dispatch and monitoring endpoints."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import Reminder
from app.services.jobs import (
    MAX_RETRIES,
    RETRY_DELAYS_MINUTES,
    dispatch_reminders,
    reminder_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reminder(app_fixture, *, send_at=None, channel="email", retry_count=0,
                   next_retry_at=None, failed=False, sent=False, retry_status="pending"):
    """Create a Reminder row inside an app context and return its id."""
    with app_fixture.app_context():
        r = Reminder(
            user_id=1,
            message="Test reminder",
            send_at=send_at or datetime.utcnow() - timedelta(minutes=1),
            channel=channel,
            retry_count=retry_count,
            next_retry_at=next_retry_at,
            failed=failed,
            sent=sent,
            retry_status=retry_status,
        )
        db.session.add(r)
        db.session.commit()
        return r.id


def _get_reminder(app_fixture, rid):
    with app_fixture.app_context():
        db.session.expire_all()
        return db.session.get(Reminder, rid)


def _register_user(app_fixture):
    """Ensure user id=1 exists in the test database."""
    from app.models import User
    import bcrypt

    with app_fixture.app_context():
        if not db.session.get(User, 1):
            u = User(
                email="jobs-test@example.com",
                password_hash=bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode(),
            )
            db.session.add(u)
            db.session.commit()


# ---------------------------------------------------------------------------
# dispatch_reminders — success path
# ---------------------------------------------------------------------------

def test_dispatch_sends_due_reminder(app_fixture):
    _register_user(app_fixture)
    rid = _make_reminder(app_fixture)

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["sent"] == 1
    assert result["processed"] == 1
    assert result["retrying"] == 0
    assert result["failed"] == 0

    r = _get_reminder(app_fixture, rid)
    assert r.sent is True
    assert r.retry_status == "sent"


def test_dispatch_skips_future_reminder(app_fixture):
    _register_user(app_fixture)
    _make_reminder(app_fixture, send_at=datetime.utcnow() + timedelta(hours=1))

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["processed"] == 0


def test_dispatch_skips_already_sent(app_fixture):
    _register_user(app_fixture)
    _make_reminder(app_fixture, sent=True, retry_status="sent")

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["processed"] == 0


def test_dispatch_skips_permanently_failed(app_fixture):
    _register_user(app_fixture)
    _make_reminder(app_fixture, failed=True, retry_status="failed")

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["processed"] == 0


# ---------------------------------------------------------------------------
# dispatch_reminders — failure / backoff path
# ---------------------------------------------------------------------------

def test_dispatch_schedules_first_retry_on_failure(app_fixture):
    _register_user(app_fixture)
    rid = _make_reminder(app_fixture)

    before = datetime.utcnow()
    with patch("app.services.jobs.send_reminder", return_value=False):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["retrying"] == 1
    assert result["sent"] == 0
    assert result["failed"] == 0

    r = _get_reminder(app_fixture, rid)
    assert r.retry_count == 1
    assert r.retry_status == "retrying"
    assert r.sent is False
    assert r.failed is False
    expected_delay = RETRY_DELAYS_MINUTES[0]
    assert r.next_retry_at >= before + timedelta(minutes=expected_delay - 1)
    assert r.last_error is not None


def test_dispatch_second_retry_uses_15min_backoff(app_fixture):
    _register_user(app_fixture)
    # Simulate first retry already scheduled and now due
    rid = _make_reminder(
        app_fixture,
        retry_count=1,
        next_retry_at=datetime.utcnow() - timedelta(seconds=1),
        retry_status="retrying",
    )

    before = datetime.utcnow()
    with patch("app.services.jobs.send_reminder", return_value=False):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["retrying"] == 1
    r = _get_reminder(app_fixture, rid)
    assert r.retry_count == 2
    expected_delay = RETRY_DELAYS_MINUTES[1]
    assert r.next_retry_at >= before + timedelta(minutes=expected_delay - 1)


def test_dispatch_third_retry_uses_45min_backoff(app_fixture):
    _register_user(app_fixture)
    rid = _make_reminder(
        app_fixture,
        retry_count=2,
        next_retry_at=datetime.utcnow() - timedelta(seconds=1),
        retry_status="retrying",
    )

    before = datetime.utcnow()
    with patch("app.services.jobs.send_reminder", return_value=False):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["retrying"] == 1
    r = _get_reminder(app_fixture, rid)
    assert r.retry_count == 3
    expected_delay = RETRY_DELAYS_MINUTES[2]
    assert r.next_retry_at >= before + timedelta(minutes=expected_delay - 1)


def test_dispatch_marks_failed_after_max_retries(app_fixture):
    _register_user(app_fixture)
    rid = _make_reminder(
        app_fixture,
        retry_count=MAX_RETRIES,
        next_retry_at=datetime.utcnow() - timedelta(seconds=1),
        retry_status="retrying",
    )

    with patch("app.services.jobs.send_reminder", return_value=False):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["failed"] == 1
    assert result["retrying"] == 0

    r = _get_reminder(app_fixture, rid)
    assert r.failed is True
    assert r.retry_status == "failed"
    assert r.sent is False


def test_dispatch_retry_due_is_processed(app_fixture):
    """A retrying reminder whose next_retry_at is in the past must be picked up."""
    _register_user(app_fixture)
    rid = _make_reminder(
        app_fixture,
        retry_count=1,
        next_retry_at=datetime.utcnow() - timedelta(minutes=10),
        retry_status="retrying",
    )

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["sent"] == 1
    r = _get_reminder(app_fixture, rid)
    assert r.sent is True
    assert r.retry_status == "sent"


def test_dispatch_retry_not_yet_due_is_skipped(app_fixture):
    """A retrying reminder whose next_retry_at is in the future must NOT be picked up."""
    _register_user(app_fixture)
    _make_reminder(
        app_fixture,
        retry_count=1,
        next_retry_at=datetime.utcnow() + timedelta(minutes=4),
        retry_status="retrying",
    )

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["processed"] == 0


def test_dispatch_captures_exception_as_error(app_fixture):
    """send_reminder raising an exception is treated as a failure."""
    _register_user(app_fixture)
    rid = _make_reminder(app_fixture)

    with patch("app.services.jobs.send_reminder", side_effect=RuntimeError("SMTP timeout")):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["retrying"] == 1
    r = _get_reminder(app_fixture, rid)
    assert "SMTP timeout" in r.last_error


def test_dispatch_processes_multiple_reminders(app_fixture):
    _register_user(app_fixture)
    for _ in range(3):
        _make_reminder(app_fixture)

    with patch("app.services.jobs.send_reminder", return_value=True):
        with app_fixture.app_context():
            result = dispatch_reminders()

    assert result["sent"] == 3
    assert result["processed"] == 3


# ---------------------------------------------------------------------------
# reminder_stats
# ---------------------------------------------------------------------------

def test_reminder_stats_counts(app_fixture):
    _register_user(app_fixture)
    # pending
    _make_reminder(app_fixture)
    # sent
    _make_reminder(app_fixture, sent=True, retry_status="sent")
    # retrying
    _make_reminder(
        app_fixture,
        retry_count=1,
        next_retry_at=datetime.utcnow() + timedelta(minutes=5),
        retry_status="retrying",
    )
    # failed
    _make_reminder(app_fixture, failed=True, retry_status="failed")

    with app_fixture.app_context():
        stats = reminder_stats()

    assert stats["total"] == 4
    assert stats["pending"] == 1
    assert stats["sent"] == 1
    assert stats["retrying"] == 1
    assert stats["failed"] == 1


# ---------------------------------------------------------------------------
# /jobs/status endpoint
# ---------------------------------------------------------------------------

def test_jobs_status_no_scheduler(client):
    r = client.get("/jobs/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["scheduler"] == "not_configured"
    assert data["jobs"] == []


def test_jobs_status_with_mock_scheduler(client, app_fixture):
    class _MockJob:
        id = "dispatch_reminders"
        name = "dispatch_reminders"
        next_run_time = datetime(2026, 3, 20, 12, 0, 0)
        trigger = "interval[0:01:00]"

    class _MockScheduler:
        running = True

        def get_jobs(self):
            return [_MockJob()]

    with app_fixture.app_context():
        app_fixture.extensions["scheduler"] = _MockScheduler()

    r = client.get("/jobs/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["scheduler"] == "running"
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["id"] == "dispatch_reminders"

    # Clean up
    with app_fixture.app_context():
        app_fixture.extensions.pop("scheduler", None)


# ---------------------------------------------------------------------------
# /jobs/reminders/stats endpoint
# ---------------------------------------------------------------------------

def test_jobs_reminders_stats_requires_auth(client):
    r = client.get("/jobs/reminders/stats")
    assert r.status_code == 401


def test_jobs_reminders_stats_returns_counts(client, auth_header, app_fixture):
    _register_user(app_fixture)
    r = client.get("/jobs/reminders/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    for key in ("total", "pending", "sent", "retrying", "failed"):
        assert key in data


# ---------------------------------------------------------------------------
# /jobs/reminders/run endpoint
# ---------------------------------------------------------------------------

def test_jobs_reminders_run_requires_auth(client):
    r = client.post("/jobs/reminders/run")
    assert r.status_code == 401


def test_jobs_reminders_run_dispatches(client, auth_header, app_fixture):
    _register_user(app_fixture)
    _make_reminder(app_fixture)

    with patch("app.services.jobs.send_reminder", return_value=True):
        r = client.post("/jobs/reminders/run", headers=auth_header)

    assert r.status_code == 200
    data = r.get_json()
    assert data["sent"] == 1
    assert data["processed"] == 1


def test_jobs_reminders_run_returns_zero_when_nothing_due(client, auth_header):
    with patch("app.services.jobs.send_reminder", return_value=True):
        r = client.post("/jobs/reminders/run", headers=auth_header)

    assert r.status_code == 200
    data = r.get_json()
    assert data["processed"] == 0


# ---------------------------------------------------------------------------
# Backoff delay constants
# ---------------------------------------------------------------------------

def test_retry_delay_constants():
    assert len(RETRY_DELAYS_MINUTES) == MAX_RETRIES
    assert RETRY_DELAYS_MINUTES == [5, 15, 45]
    # Each delay is larger than the previous (exponential growth)
    for i in range(1, len(RETRY_DELAYS_MINUTES)):
        assert RETRY_DELAYS_MINUTES[i] > RETRY_DELAYS_MINUTES[i - 1]
