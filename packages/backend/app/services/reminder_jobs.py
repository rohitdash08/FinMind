from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..extensions import db
from ..models import Reminder


BACKOFF_MINUTES = (5, 15, 45)


@dataclass
class ReminderRunResult:
    processed: int = 0
    sent: int = 0
    retrying: int = 0
    failed: int = 0
    sent_channels: list[str] | None = None

    def to_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "sent": self.sent,
            "retrying": self.retrying,
            "failed": self.failed,
        }


def due_reminders_query(user_id: int, now: datetime):
    return (
        db.session.query(Reminder)
        .filter(
            Reminder.user_id == user_id,
            Reminder.sent.is_(False),
            Reminder.retry_status != "FAILED",
            Reminder.send_at <= now,
        )
        .filter((Reminder.next_retry_at.is_(None)) | (Reminder.next_retry_at <= now))
        .order_by(Reminder.send_at, Reminder.id)
    )


def process_due_reminders(
    *,
    user_id: int,
    now: datetime,
    sender: Callable[[Reminder], bool],
) -> ReminderRunResult:
    result = ReminderRunResult()
    reminders = due_reminders_query(user_id, now).all()
    for reminder in reminders:
        result.processed += 1
        reminder.last_attempt_at = now
        try:
            ok = bool(sender(reminder))
        except Exception as exc:  # pragma: no cover - exercised through route tests
            ok = False
            reminder.last_error = str(exc)[:500]

        if ok:
            reminder.sent = True
            reminder.retry_status = "SENT"
            reminder.next_retry_at = None
            reminder.last_error = None
            result.sent += 1
            if result.sent_channels is None:
                result.sent_channels = []
            result.sent_channels.append(reminder.channel)
            continue

        if not reminder.last_error:
            reminder.last_error = "sender returned false"
        reminder.retry_count += 1
        if reminder.retry_count >= reminder.max_retries:
            reminder.retry_status = "FAILED"
            reminder.failed_at = now
            reminder.next_retry_at = None
            result.failed += 1
        else:
            reminder.retry_status = "RETRYING"
            reminder.next_retry_at = next_retry_time(now, reminder.retry_count)
            result.retrying += 1

    db.session.commit()
    return result


def next_retry_time(now: datetime, retry_count: int) -> datetime:
    index = min(max(retry_count - 1, 0), len(BACKOFF_MINUTES) - 1)
    return now + timedelta(minutes=BACKOFF_MINUTES[index])


def reset_failed_reminder(reminder: Reminder) -> None:
    reminder.retry_status = "PENDING"
    reminder.retry_count = 0
    reminder.next_retry_at = None
    reminder.last_error = None
    reminder.failed_at = None
    reminder.sent = False
