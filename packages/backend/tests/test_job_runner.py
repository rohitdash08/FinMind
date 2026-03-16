"""
Tests for resilient background job retry & monitoring (Issue #130).

Covers:
- Successful reminder dispatch marks sent=True and records a JobRun
- Failed dispatch increments retry_count and schedules next_retry_at
- After max_retries failures, reminder is marked failed_permanently
- Exponential backoff schedule is correct
- /reminders/run returns stats dict
- /reminders/job-runs returns audit records
- Retryable reminders are re-queued on next run
- Reminders not yet due are skipped
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import JobRun, Reminder, User
from app.services.job_runner import run_due_reminders


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_user(app_ctx) -> int:
    import uuid
    from app.extensions import db as _db
    from werkzeug.security import generate_password_hash

    email = f"runner_{uuid.uuid4().hex[:8]}@test.com"
    u = User(email=email, password_hash=generate_password_hash("x"))
    _db.session.add(u)
    _db.session.flush()
    return u.id


def _make_reminder(user_id: int, *, send_at=None, max_retries: int = 3) -> Reminder:
    r = Reminder(
        user_id=user_id,
        message="Test reminder",
        send_at=send_at or datetime.utcnow() - timedelta(minutes=1),
        channel="email",
        max_retries=max_retries,
    )
    db.session.add(r)
    db.session.flush()
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Tests – job_runner service
# ─────────────────────────────────────────────────────────────────────────────


class TestRunDueReminders:
    def test_successful_dispatch_marks_sent(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            r = _make_reminder(uid)
            rid = r.id

            with patch("app.services.job_runner.send_reminder", return_value=True):
                stats = run_due_reminders(user_id=uid)

            reminder = db.session.get(Reminder, rid)
            assert reminder.sent is True
            assert reminder.retry_count == 0
            assert reminder.failed_permanently is False
            assert reminder.last_error is None

            assert stats["processed"] == 1
            assert stats["succeeded"] == 1
            assert stats["errors"] == 0

    def test_failed_dispatch_increments_retry_count(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            r = _make_reminder(uid)
            rid = r.id

            with patch("app.services.job_runner.send_reminder", return_value=False):
                stats = run_due_reminders(user_id=uid)

            reminder = db.session.get(Reminder, rid)
            assert reminder.sent is False
            assert reminder.retry_count == 1
            assert reminder.failed_permanently is False
            assert reminder.next_retry_at is not None
            assert reminder.next_retry_at > datetime.utcnow()
            assert stats["errors"] == 1

    def test_exponential_backoff_schedule(self, app_fixture):
        """next_retry_at should be ~2^retry_count minutes ahead."""
        with app_fixture.app_context():
            uid = _make_user(app_fixture)

            with patch("app.services.job_runner.send_reminder", return_value=False):
                # First failure → retry_count=1 → backoff=2 min
                r = _make_reminder(uid)
                run_due_reminders(user_id=uid)
                db.session.refresh(r)
                assert r.retry_count == 1
                expected_backoff = timedelta(minutes=2)
                actual_backoff = r.next_retry_at - datetime.utcnow()
                # Allow 5-second tolerance
                assert abs(actual_backoff.total_seconds() - expected_backoff.total_seconds()) < 5

    def test_permanently_failed_after_max_retries(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            r = _make_reminder(uid, max_retries=2)
            rid = r.id

            with patch("app.services.job_runner.send_reminder", return_value=False):
                # First run → retry_count=1
                run_due_reminders(user_id=uid)
                db.session.refresh(r)
                assert r.failed_permanently is False

                # Force next_retry_at to the past so it gets picked up again
                r.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
                db.session.commit()

                # Second run → retry_count=2 >= max_retries=2 → permanently failed
                run_due_reminders(user_id=uid)

            reminder = db.session.get(Reminder, rid)
            assert reminder.failed_permanently is True
            assert reminder.sent is False

    def test_permanently_failed_not_retried(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            r = _make_reminder(uid)
            r.failed_permanently = True
            db.session.commit()

            with patch("app.services.job_runner.send_reminder") as mock_send:
                stats = run_due_reminders(user_id=uid)

            mock_send.assert_not_called()
            assert stats["processed"] == 0

    def test_future_reminder_skipped(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            _make_reminder(uid, send_at=datetime.utcnow() + timedelta(hours=2))

            with patch("app.services.job_runner.send_reminder") as mock_send:
                stats = run_due_reminders(user_id=uid)

            mock_send.assert_not_called()
            assert stats["processed"] == 0

    def test_not_yet_due_retry_skipped(self, app_fixture):
        """A reminder waiting for its next_retry_at in the future should be skipped."""
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            r = _make_reminder(uid)
            r.retry_count = 1
            r.next_retry_at = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()

            with patch("app.services.job_runner.send_reminder") as mock_send:
                stats = run_due_reminders(user_id=uid)

            mock_send.assert_not_called()
            assert stats["processed"] == 0

    def test_job_run_record_created(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            _make_reminder(uid)

            before = datetime.utcnow()
            with patch("app.services.job_runner.send_reminder", return_value=True):
                run_due_reminders(user_id=uid)

            runs = db.session.query(JobRun).filter_by(job_name="reminder_dispatch").all()
            assert len(runs) == 1
            run = runs[0]
            assert run.status == "success"
            assert run.processed == 1
            assert run.succeeded == 1
            assert run.errors == 0
            assert run.finished_at is not None
            assert run.finished_at >= before

    def test_job_run_partial_on_mixed_results(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            _make_reminder(uid)
            _make_reminder(uid)

            results = iter([True, False])
            with patch(
                "app.services.job_runner.send_reminder", side_effect=lambda _: next(results)
            ):
                run_due_reminders(user_id=uid)

            run = db.session.query(JobRun).filter_by(job_name="reminder_dispatch").first()
            assert run.status == "partial"

    def test_exception_during_send_treated_as_failure(self, app_fixture):
        with app_fixture.app_context():
            uid = _make_user(app_fixture)
            r = _make_reminder(uid)

            with patch(
                "app.services.job_runner.send_reminder",
                side_effect=RuntimeError("SMTP connection refused"),
            ):
                stats = run_due_reminders(user_id=uid)

            db.session.refresh(r)
            assert r.retry_count == 1
            assert "SMTP connection refused" in (r.last_error or "")
            assert stats["errors"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests – HTTP endpoints
# ─────────────────────────────────────────────────────────────────────────────


class TestReminderRunEndpoint:
    def test_run_returns_stats_dict(self, client, auth_header):
        with patch("app.routes.reminders.run_due_reminders", return_value={
            "processed": 0, "succeeded": 0, "errors": 0,
            "retried": 0, "permanently_failed": 0,
        }):
            resp = client.post("/reminders/run", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "processed" in data
        assert "succeeded" in data
        assert "errors" in data

    def test_run_requires_auth(self, client):
        resp = client.post("/reminders/run")
        assert resp.status_code == 401


class TestJobRunsEndpoint:
    def test_job_runs_empty(self, client, auth_header):
        resp = client.get("/reminders/job-runs", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_job_runs_returns_records(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            jr = JobRun(
                job_name="reminder_dispatch",
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                status="success",
                processed=2,
                succeeded=2,
                errors=0,
                retried=0,
            )
            db.session.add(jr)
            db.session.commit()

        resp = client.get("/reminders/job-runs", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["status"] == "success"
        assert data[0]["processed"] == 2

    def test_job_runs_requires_auth(self, client):
        resp = client.get("/reminders/job-runs")
        assert resp.status_code == 401

    def test_job_runs_limit(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            for i in range(5):
                db.session.add(JobRun(
                    job_name="reminder_dispatch",
                    started_at=datetime.utcnow(),
                    status="success",
                ))
            db.session.commit()

        resp = client.get("/reminders/job-runs?limit=3", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 3
