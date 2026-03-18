"""
Tests for the resilient background job retry system.

Coverage:
  - backoff_delta helper (4 cases)
  - dispatch_reminders core logic (14 cases — no DB or scheduler needed)
  - /jobs/status endpoint (3 cases)
  - /jobs/reminders/stats endpoint (4 cases)
  - /jobs/reminders/run endpoint (3 cases)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token

# Force testing env before any app import
os.environ.setdefault("FLASK_ENV", "testing")

from app.services.scheduler import (
    MAX_RETRIES,
    _RETRY_DELAYS,
    backoff_delta,
    dispatch_reminders,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reminder(**kwargs) -> SimpleNamespace:
    """Return a lightweight Reminder-like object with sensible defaults."""
    now = datetime.utcnow()
    r = SimpleNamespace(
        id=kwargs.get("id", 1),
        sent=kwargs.get("sent", False),
        failed=kwargs.get("failed", False),
        retry_count=kwargs.get("retry_count", 0),
        send_at=kwargs.get("send_at", now - timedelta(minutes=1)),
        next_retry_at=kwargs.get("next_retry_at", None),
        last_error=kwargs.get("last_error", None),
        last_retry_at=kwargs.get("last_retry_at", None),
        retry_status=kwargs.get("retry_status", "pending"),
    )
    return r


def _ok(_reminder) -> bool:
    return True


def _fail(_reminder) -> bool:
    return False


# ---------------------------------------------------------------------------
# Local fixtures — bypass Redis-dependent login route
# ---------------------------------------------------------------------------

@pytest.fixture()
def token_header(app_fixture):
    """JWT auth header for a regular user — no Redis required."""
    with app_fixture.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash

        user = User(
            email="jobs_user@example.com",
            password_hash=generate_password_hash("pw"),
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": "USER"},
        )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_token_header(app_fixture):
    """JWT auth header for an admin user — no Redis required."""
    with app_fixture.app_context():
        from app.extensions import db
        from app.models import User, Role
        from werkzeug.security import generate_password_hash

        user = User(
            email="jobs_admin@example.com",
            password_hash=generate_password_hash("pw"),
            role=Role.ADMIN.value,
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": "ADMIN"},
        )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. backoff_delta
# ---------------------------------------------------------------------------

class TestBackoffDelta:
    def test_first_retry_is_5_minutes(self):
        assert backoff_delta(0) == timedelta(minutes=5)

    def test_second_retry_is_15_minutes(self):
        assert backoff_delta(1) == timedelta(minutes=15)

    def test_third_retry_is_45_minutes(self):
        assert backoff_delta(2) == timedelta(minutes=45)

    def test_beyond_max_is_capped_at_last_delay(self):
        assert backoff_delta(99) == timedelta(minutes=_RETRY_DELAYS[-1])


# ---------------------------------------------------------------------------
# 2. dispatch_reminders — pure core logic
# ---------------------------------------------------------------------------

class TestDispatchReminders:
    def test_dispatches_due_reminder_successfully(self):
        r = _make_reminder()
        summary = dispatch_reminders([r], _ok)
        assert r.sent is True
        assert r.retry_status == "sent"
        assert summary["dispatched"] == 1

    def test_skips_future_reminder_on_first_attempt(self):
        r = _make_reminder(
            send_at=datetime.utcnow() + timedelta(hours=1),
            retry_count=0,
        )
        summary = dispatch_reminders([r], _ok)
        assert r.sent is False
        assert summary["skipped"] == 1

    def test_skips_reminder_in_retry_backoff_window(self):
        r = _make_reminder(
            retry_count=1,
            next_retry_at=datetime.utcnow() + timedelta(minutes=10),
        )
        summary = dispatch_reminders([r], _ok)
        assert r.sent is False
        assert summary["skipped"] == 1

    def test_increments_retry_count_on_first_failure(self):
        r = _make_reminder()
        dispatch_reminders([r], _fail)
        assert r.retry_count == 1

    def test_sets_next_retry_at_after_first_failure(self):
        r = _make_reminder()
        now = datetime.utcnow()
        dispatch_reminders([r], _fail, now=now)
        expected = now + timedelta(minutes=5)
        assert r.next_retry_at == expected

    def test_retry_status_is_retrying_after_partial_failure(self):
        r = _make_reminder()
        dispatch_reminders([r], _fail)
        assert r.retry_status == "retrying"

    def test_marks_permanently_failed_after_max_retries(self):
        r = _make_reminder(retry_count=MAX_RETRIES - 1)
        dispatch_reminders([r], _fail)
        assert r.failed is True
        assert r.retry_count == MAX_RETRIES
        assert r.retry_status == "failed"

    def test_retry_count_in_summary_for_retrying_reminders(self):
        r = _make_reminder(retry_count=MAX_RETRIES - 2)
        summary = dispatch_reminders([r], _fail)
        assert summary["retried"] == 1

    def test_permanently_failed_in_summary(self):
        r = _make_reminder(retry_count=MAX_RETRIES - 1)
        summary = dispatch_reminders([r], _fail)
        assert summary["failed_permanently"] == 1

    def test_successful_retry_counts_as_retried_not_dispatched(self):
        r = _make_reminder(retry_count=1)
        summary = dispatch_reminders([r], _ok)
        assert summary["dispatched"] == 0
        assert summary["retried"] == 1

    def test_sender_exception_is_caught_and_recorded(self):
        r = _make_reminder()

        def boom(_r):
            raise RuntimeError("SMTP error")

        # Must not propagate
        dispatch_reminders([r], boom)
        assert r.last_error == "SMTP error"
        assert r.retry_count == 1

    def test_multiple_reminders_processed_independently(self):
        r1 = _make_reminder(id=1)
        r2 = _make_reminder(id=2)
        r3 = _make_reminder(id=3, retry_count=MAX_RETRIES - 1)

        calls = iter([True, False, False])
        sender = lambda r: next(calls)  # noqa: E731

        summary = dispatch_reminders([r1, r2, r3], sender)
        assert r1.sent is True
        assert r2.retry_count == 1
        assert r3.failed is True
        assert summary["dispatched"] == 1
        assert summary["retried"] == 1
        assert summary["failed_permanently"] == 1

    def test_last_error_cleared_on_successful_delivery(self):
        r = _make_reminder(retry_count=1, last_error="previous error")
        dispatch_reminders([r], _ok)
        assert r.last_error is None

    def test_empty_candidates_returns_zero_summary(self):
        summary = dispatch_reminders([], _ok)
        assert summary == {
            "dispatched": 0,
            "retried": 0,
            "failed_permanently": 0,
            "skipped": 0,
        }


# ---------------------------------------------------------------------------
# 3. Endpoint tests
# ---------------------------------------------------------------------------

class TestJobsStatusEndpoint:
    def test_status_requires_auth(self, client):
        r = client.get("/jobs/status")
        assert r.status_code == 401

    def test_status_returns_200_with_auth(self, client, token_header):
        r = client.get("/jobs/status", headers=token_header)
        assert r.status_code == 200

    def test_status_reports_scheduler_as_not_running_in_test_env(
        self, client, token_header
    ):
        r = client.get("/jobs/status", headers=token_header)
        data = r.get_json()
        assert "running" in data
        # FLASK_ENV=testing → scheduler is disabled
        assert data["running"] is False
        assert isinstance(data["jobs"], list)


class TestRemindersStatsEndpoint:
    def test_stats_requires_auth(self, client):
        r = client.get("/jobs/reminders/stats")
        assert r.status_code == 401

    def test_stats_returns_200_with_auth(self, client, token_header):
        r = client.get("/jobs/reminders/stats", headers=token_header)
        assert r.status_code == 200

    def test_stats_response_has_all_expected_keys(self, client, token_header):
        r = client.get("/jobs/reminders/stats", headers=token_header)
        data = r.get_json()
        for key in (
            "total",
            "sent",
            "pending",
            "overdue",
            "retrying",
            "permanently_failed",
        ):
            assert key in data, f"Missing key in stats: {key}"

    def test_stats_counts_a_future_reminder_as_pending(
        self, client, app_fixture, token_header
    ):
        with app_fixture.app_context():
            from app.extensions import db
            from app.models import Reminder, User

            user = db.session.query(User).filter_by(
                email="jobs_user@example.com"
            ).first()
            future = datetime.utcnow() + timedelta(hours=2)
            db.session.add(
                Reminder(
                    user_id=user.id,
                    message="Pay bill",
                    send_at=future,
                    channel="email",
                )
            )
            db.session.commit()

        resp = client.get("/jobs/reminders/stats", headers=token_header)
        data = resp.get_json()
        assert data["total"] >= 1
        assert data["pending"] >= 1


class TestRunRemindersEndpoint:
    def test_run_requires_auth(self, client):
        r = client.post("/jobs/reminders/run")
        assert r.status_code == 401

    def test_run_returns_403_for_regular_user(self, client, token_header):
        r = client.post("/jobs/reminders/run", headers=token_header)
        assert r.status_code == 403

    def test_run_returns_200_for_admin(self, client, admin_token_header):
        r = client.post("/jobs/reminders/run", headers=admin_token_header)
        assert r.status_code == 200
        data = r.get_json()
        for key in ("dispatched", "retried", "failed_permanently", "skipped"):
            assert key in data
