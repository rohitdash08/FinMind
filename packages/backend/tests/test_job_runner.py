"""
Tests for resilient background job retry & monitoring (issue #130).

Covers:
- RetryPolicy exponential backoff calculation
- process_due_reminders: success, failures, retries, dead-letter
- Crash recovery for stale "sending" reminders
- Dead-letter reset
- Job stats aggregation
- Admin API endpoints: /jobs/status, /jobs/failed, /jobs/run, /jobs/retry-dead
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_login(client, email="job@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_reminder(client, headers, overrides=None):
    """Create a reminder via API and return the id."""
    payload = {
        "message": "Test reminder",
        "send_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
        "channel": "email",
    }
    if overrides:
        payload.update(overrides)
    r = client.post("/reminders", json=payload, headers=headers)
    assert r.status_code == 201
    return r.get_json()["id"]


# ---------------------------------------------------------------------------
# Unit tests: RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_default_delays(self):
        from app.services.job_runner import RetryPolicy

        p = RetryPolicy()
        assert p.delay_for_attempt(0) == 60   # base
        assert p.delay_for_attempt(1) == 180  # 60 * 3
        assert p.delay_for_attempt(2) == 540  # 60 * 9

    def test_delay_capped(self):
        from app.services.job_runner import RetryPolicy

        p = RetryPolicy(max_delay_seconds=120)
        assert p.delay_for_attempt(5) == 120  # capped

    def test_custom_policy(self):
        from app.services.job_runner import RetryPolicy

        p = RetryPolicy(base_delay_seconds=10, backoff_factor=2.0)
        assert p.delay_for_attempt(0) == 10
        assert p.delay_for_attempt(1) == 20
        assert p.delay_for_attempt(2) == 40


# ---------------------------------------------------------------------------
# Integration tests: job runner
# ---------------------------------------------------------------------------


class TestProcessDueReminders:
    @patch("app.services.job_runner.send_reminder", return_value=True)
    def test_success_marks_sent(self, mock_send, client, app_fixture):
        headers = _register_and_login(client)
        rid = _create_reminder(client, headers)

        from app.services.job_runner import process_due_reminders

        with app_fixture.app_context():
            result = process_due_reminders(batch_size=10)

        assert result.processed == 1
        assert result.succeeded == 1
        assert result.failed == 0

        # Verify DB state
        with app_fixture.app_context():
            from app.models import Reminder
            from app.extensions import db

            r = db.session.get(Reminder, rid)
            assert r.status == "sent"
            assert r.sent is True
            assert r.completed_at is not None

    @patch("app.services.job_runner.send_reminder", return_value=False)
    def test_failure_schedules_retry(self, mock_send, client, app_fixture):
        headers = _register_and_login(client)
        rid = _create_reminder(client, headers)

        from app.services.job_runner import process_due_reminders

        with app_fixture.app_context():
            result = process_due_reminders(batch_size=10)

        assert result.processed == 1
        assert result.failed == 1
        assert result.succeeded == 0

        with app_fixture.app_context():
            from app.models import Reminder
            from app.extensions import db

            r = db.session.get(Reminder, rid)
            assert r.status == "failed"
            assert r.retry_count == 1
            assert r.last_error == "delivery returned false"
            assert r.next_retry_at is not None

    @patch("app.services.job_runner.send_reminder", return_value=False)
    def test_dead_letter_after_max_retries(self, mock_send, client, app_fixture):
        headers = _register_and_login(client)
        rid = _create_reminder(client, headers)

        from app.services.job_runner import process_due_reminders, RetryPolicy

        policy = RetryPolicy(max_retries=2, base_delay_seconds=0)

        with app_fixture.app_context():
            # First failure → retry_count=1, status=failed
            process_due_reminders(batch_size=10, policy=policy)
            from app.models import Reminder
            from app.extensions import db

            r = db.session.get(Reminder, rid)
            assert r.status == "failed"
            assert r.retry_count == 1

            # Make next_retry_at in the past so it's eligible
            r.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

            # Second failure → retry_count=2 >= max_retries → dead
            result = process_due_reminders(batch_size=10, policy=policy)
            r = db.session.get(Reminder, rid)
            assert r.status == "dead"
            assert r.retry_count == 2
            assert result.dead_lettered == 1

    @patch("app.services.job_runner.send_reminder", side_effect=Exception("network error"))
    def test_exception_handled_gracefully(self, mock_send, client, app_fixture):
        headers = _register_and_login(client)
        rid = _create_reminder(client, headers)

        from app.services.job_runner import process_due_reminders

        with app_fixture.app_context():
            result = process_due_reminders(batch_size=10)

        assert result.processed == 1
        assert result.failed == 1

        with app_fixture.app_context():
            from app.models import Reminder
            from app.extensions import db

            r = db.session.get(Reminder, rid)
            assert r.status == "failed"
            assert "network error" in r.last_error

    def test_skips_future_reminders(self, client, app_fixture):
        headers = _register_and_login(client)
        # Create reminder in the future
        _create_reminder(client, headers, {
            "send_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        })

        from app.services.job_runner import process_due_reminders

        with app_fixture.app_context():
            result = process_due_reminders(batch_size=10)

        assert result.processed == 0

    @patch("app.services.job_runner.send_reminder", return_value=True)
    def test_processes_across_users(self, mock_send, client, app_fixture):
        h1 = _register_and_login(client, "user1@test.com", "pass1234")
        h2 = _register_and_login(client, "user2@test.com", "pass1234")
        _create_reminder(client, h1)
        _create_reminder(client, h2)

        from app.services.job_runner import process_due_reminders

        with app_fixture.app_context():
            result = process_due_reminders(batch_size=10)

        assert result.processed == 2
        assert result.succeeded == 2


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    def test_stale_sending_recovered(self, client, app_fixture):
        headers = _register_and_login(client)
        rid = _create_reminder(client, headers)

        from app.services.job_runner import process_due_reminders, RetryPolicy
        from app.models import Reminder
        from app.extensions import db

        # Simulate a crash: set status to "sending" with old started_at
        with app_fixture.app_context():
            r = db.session.get(Reminder, rid)
            r.status = "sending"
            r.started_at = datetime.utcnow() - timedelta(minutes=20)
            db.session.commit()

        with app_fixture.app_context():
            policy = RetryPolicy(stale_timeout_seconds=600)
            result = process_due_reminders(batch_size=10, policy=policy)
            assert result.recovered == 1

            r = db.session.get(Reminder, rid)
            assert r.status in ("failed", "sending", "sent")  # recovered from stale


# ---------------------------------------------------------------------------
# Dead-letter management
# ---------------------------------------------------------------------------


class TestDeadLetterManagement:
    def test_retry_dead_letters(self, client, app_fixture):
        headers = _register_and_login(client)
        rid = _create_reminder(client, headers)

        from app.models import Reminder
        from app.extensions import db
        from app.services.job_runner import retry_dead_letters

        with app_fixture.app_context():
            r = db.session.get(Reminder, rid)
            r.status = "dead"
            r.retry_count = 3
            r.last_error = "max retries exceeded"
            db.session.commit()

        with app_fixture.app_context():
            count = retry_dead_letters(limit=10)
            assert count == 1

            r = db.session.get(Reminder, rid)
            assert r.status == "pending"
            assert r.retry_count == 0
            assert r.last_error is None


# ---------------------------------------------------------------------------
# Job stats
# ---------------------------------------------------------------------------


class TestJobStats:
    def test_stats_aggregation(self, client, app_fixture):
        headers = _register_and_login(client)

        from app.models import Reminder
        from app.extensions import db
        from app.services.job_runner import get_job_stats

        with app_fixture.app_context():
            # Create reminders with various statuses
            for status in ["pending", "pending", "sent", "failed", "dead"]:
                r = Reminder(
                    user_id=1,
                    message="test",
                    send_at=datetime.utcnow(),
                    channel="email",
                    status=status,
                )
                db.session.add(r)
            db.session.commit()

            stats = get_job_stats()
            assert stats["pending"] == 2
            assert stats["sent"] == 1
            assert stats["failed"] == 1
            assert stats["dead"] == 1
            assert stats["total"] == 5


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestJobsAPI:
    def test_status_endpoint(self, client, app_fixture):
        headers = _register_and_login(client)
        r = client.get("/jobs/status", headers=headers)
        assert r.status_code == 200
        data = r.get_json()
        assert "scheduler" in data
        assert "stats" in data

    def test_status_requires_auth(self, client):
        r = client.get("/jobs/status")
        assert r.status_code in (401, 422)

    def test_failed_endpoint(self, client, app_fixture):
        headers = _register_and_login(client)
        r = client.get("/jobs/failed", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    @patch("app.services.job_runner.send_reminder", return_value=True)
    def test_manual_run_endpoint(self, mock_send, client, app_fixture):
        headers = _register_and_login(client)
        _create_reminder(client, headers)

        r = client.post("/jobs/run", headers=headers)
        assert r.status_code == 200
        data = r.get_json()
        assert data["processed"] == 1
        assert data["succeeded"] == 1

    def test_retry_dead_endpoint(self, client, app_fixture):
        headers = _register_and_login(client)
        r = client.post("/jobs/retry-dead", headers=headers)
        assert r.status_code == 200
        assert "reset" in r.get_json()

    def test_failed_with_status_filter(self, client, app_fixture):
        headers = _register_and_login(client)
        r = client.get("/jobs/failed?status=dead", headers=headers)
        assert r.status_code == 200
