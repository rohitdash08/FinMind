from datetime import datetime, timedelta

from app.models import Reminder
from app.services.reminder_jobs import mark_reminder_attempt, process_due_reminders


def _reminder():
    return Reminder(
        user_id=1,
        message="Pay electricity bill",
        send_at=datetime.utcnow() - timedelta(minutes=1),
        sent=False,
        failed=False,
        retry_count=0,
        max_retries=3,
        channel="email",
    )


def test_successful_attempt_marks_sent_and_clears_retry_state():
    now = datetime.utcnow()
    reminder = _reminder()
    reminder.retry_count = 2
    reminder.next_retry_at = now
    reminder.last_error = "previous failure"

    outcome = mark_reminder_attempt(reminder, delivered=True, now=now)

    assert outcome == "sent"
    assert reminder.sent is True
    assert reminder.failed is False
    assert reminder.next_retry_at is None
    assert reminder.last_error is None
    assert reminder.last_attempt_at == now


def test_failed_attempt_schedules_exponential_retry_before_max_retries():
    now = datetime.utcnow()
    reminder = _reminder()
    reminder.max_retries = 3

    outcome = mark_reminder_attempt(
        reminder,
        delivered=False,
        now=now,
        error="smtp timeout",
    )

    assert outcome == "retry_scheduled"
    assert reminder.sent is False
    assert reminder.failed is False
    assert reminder.retry_count == 1
    assert reminder.last_error == "smtp timeout"
    assert reminder.next_retry_at == now + timedelta(minutes=5)


def test_failed_attempt_marks_permanently_failed_at_max_retries():
    now = datetime.utcnow()
    reminder = _reminder()
    reminder.retry_count = 2
    reminder.max_retries = 3

    outcome = mark_reminder_attempt(
        reminder,
        delivered=False,
        now=now,
        error="provider rejected message",
    )

    assert outcome == "failed"
    assert reminder.sent is False
    assert reminder.failed is True
    assert reminder.retry_count == 3
    assert reminder.next_retry_at is None
    assert reminder.last_error == "provider rejected message"


def test_process_due_reminders_tracks_mixed_outcomes():
    now = datetime.utcnow()
    first = _reminder()
    second = _reminder()
    third = _reminder()
    third.retry_count = 2

    def sender(reminder):
        if reminder is first:
            return True
        if reminder is second:
            return False
        raise RuntimeError("boom")

    result = process_due_reminders([first, second, third], now=now, sender=sender)

    assert result.processed == 3
    assert result.sent == 1
    assert result.retry_scheduled == 1
    assert result.failed == 1
    assert first.sent is True
    assert second.next_retry_at == now + timedelta(minutes=5)
    assert third.failed is True
    assert third.last_error == "boom"
