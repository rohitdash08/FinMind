from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..models import Reminder
from .reminders import send_reminder


DEFAULT_RETRY_DELAYS = (
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=45),
)


@dataclass(frozen=True)
class ReminderJobResult:
    processed: int = 0
    sent: int = 0
    retry_scheduled: int = 0
    failed: int = 0


def _truncate_error(error: object, limit: int = 500) -> str:
    text = str(error or "Reminder delivery failed")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _retry_delay_for(retry_count: int) -> timedelta:
    if retry_count <= 0:
        return DEFAULT_RETRY_DELAYS[0]
    index = min(retry_count, len(DEFAULT_RETRY_DELAYS) - 1)
    return DEFAULT_RETRY_DELAYS[index]


def mark_reminder_attempt(
    reminder: Reminder,
    *,
    delivered: bool,
    now: datetime,
    error: object | None = None,
) -> str:
    """Apply retry state for one reminder delivery attempt.

    Returns one of: ``sent``, ``retry_scheduled``, or ``failed``.
    """

    reminder.last_attempt_at = now

    if delivered:
        reminder.sent = True
        reminder.failed = False
        reminder.next_retry_at = None
        reminder.last_error = None
        return "sent"

    reminder.retry_count = (reminder.retry_count or 0) + 1
    reminder.last_error = _truncate_error(error)

    max_retries = reminder.max_retries if reminder.max_retries is not None else 3
    if reminder.retry_count >= max_retries:
        reminder.failed = True
        reminder.next_retry_at = None
        return "failed"

    reminder.failed = False
    reminder.next_retry_at = now + _retry_delay_for(reminder.retry_count - 1)
    return "retry_scheduled"


def process_due_reminders(
    reminders: list[Reminder],
    *,
    now: datetime,
    sender: Callable[[Reminder], bool] = send_reminder,
) -> ReminderJobResult:
    """Send due reminders and persist retry metadata on each model instance.

    The caller owns transaction commit/rollback. This function is deliberately
    pure with respect to database access so it can be tested without a scheduler
    or worker process.
    """

    counts = {"processed": 0, "sent": 0, "retry_scheduled": 0, "failed": 0}
    for reminder in reminders:
        counts["processed"] += 1
        try:
            delivered = bool(sender(reminder))
            outcome = mark_reminder_attempt(reminder, delivered=delivered, now=now)
        except Exception as exc:  # pragma: no cover - covered by route-level tests
            outcome = mark_reminder_attempt(
                reminder,
                delivered=False,
                now=now,
                error=exc,
            )
        counts[outcome] += 1

    return ReminderJobResult(**counts)
