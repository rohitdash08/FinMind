from __future__ import annotations

from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func, or_

from ..extensions import db
from ..models import Reminder
from ..observability import track_reminder_event
from .reminders import send_reminder

PENDING = "PENDING"
RETRYING = "RETRYING"
SENT = "SENT"
FAILED = "FAILED"
ACTIVE_STATUSES = {PENDING, RETRYING}
VALID_STATUSES = {PENDING, RETRYING, SENT, FAILED}
DEFAULT_RETRY_DELAYS = (300, 900, 2700)
MAX_ERROR_LENGTH = 1000


def configured_max_attempts() -> int:
    raw = current_app.config.get("REMINDER_JOB_MAX_ATTEMPTS", 3)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 3


def configured_retry_delays() -> tuple[int, ...]:
    raw = current_app.config.get("REMINDER_JOB_BACKOFF_SECONDS")
    if not raw:
        return DEFAULT_RETRY_DELAYS
    if isinstance(raw, str):
        pieces = raw.split(",")
    else:
        pieces = list(raw)

    delays: list[int] = []
    for piece in pieces:
        try:
            delay = int(str(piece).strip())
        except (TypeError, ValueError):
            continue
        if delay > 0:
            delays.append(delay)
    return tuple(delays) or DEFAULT_RETRY_DELAYS


def serialize_reminder_job(reminder: Reminder) -> dict:
    return {
        "id": reminder.id,
        "message": reminder.message,
        "send_at": _iso(reminder.send_at),
        "sent": reminder.sent,
        "channel": reminder.channel,
        "job_status": reminder.job_status,
        "retry_count": reminder.retry_count,
        "max_attempts": reminder.max_attempts,
        "next_retry_at": _iso(reminder.next_retry_at),
        "last_attempt_at": _iso(reminder.last_attempt_at),
        "sent_at": _iso(reminder.sent_at),
        "failed_at": _iso(reminder.failed_at),
        "last_error": reminder.last_error,
    }


def process_due_reminders(user_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    reminders = (
        _due_reminders_query(user_id=user_id, now=now)
        .order_by(Reminder.send_at.asc(), Reminder.id.asc())
        .all()
    )
    summary = {
        "processed": len(reminders),
        "sent": 0,
        "retrying": 0,
        "failed": 0,
    }
    for reminder in reminders:
        result = attempt_reminder_delivery(reminder, now=now)
        if result["job_status"] == SENT:
            summary["sent"] += 1
        elif result["job_status"] == RETRYING:
            summary["retrying"] += 1
        elif result["job_status"] == FAILED:
            summary["failed"] += 1
    db.session.commit()
    return summary


def attempt_reminder_delivery(reminder: Reminder, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    _ensure_retry_defaults(reminder)
    reminder.last_attempt_at = now

    try:
        delivered = bool(send_reminder(reminder))
        error = None if delivered else "send_reminder returned false"
    except Exception as exc:  # pragma: no cover - explicit tests monkeypatch this
        delivered = False
        error = str(exc) or exc.__class__.__name__

    if delivered:
        reminder.sent = True
        reminder.job_status = SENT
        reminder.sent_at = now
        reminder.failed_at = None
        reminder.next_retry_at = None
        reminder.last_error = None
        track_reminder_event(event="sent", channel=reminder.channel)
        return {"job_status": SENT, "error": None}

    reminder.sent = False
    reminder.retry_count = (reminder.retry_count or 0) + 1
    reminder.last_error = _truncate_error(error)

    if reminder.retry_count >= reminder.max_attempts:
        reminder.job_status = FAILED
        reminder.failed_at = now
        reminder.next_retry_at = None
        track_reminder_event(
            event="failed", channel=reminder.channel, status="delivery_error"
        )
        return {"job_status": FAILED, "error": reminder.last_error}

    reminder.job_status = RETRYING
    reminder.failed_at = None
    reminder.next_retry_at = now + timedelta(
        seconds=_delay_for_failure(reminder.retry_count)
    )
    track_reminder_event(
        event="retry_scheduled", channel=reminder.channel, status="delivery_error"
    )
    return {"job_status": RETRYING, "error": reminder.last_error}


def reset_reminder_for_retry(reminder: Reminder) -> None:
    _ensure_retry_defaults(reminder)
    reminder.sent = False
    reminder.job_status = PENDING
    reminder.retry_count = 0
    reminder.next_retry_at = None
    reminder.sent_at = None
    reminder.failed_at = None
    reminder.last_error = None
    track_reminder_event(event="manual_retry", channel=reminder.channel)


def reminder_job_stats(user_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    counts = dict(
        db.session.query(Reminder.job_status, func.count(Reminder.id))
        .filter(Reminder.user_id == user_id)
        .group_by(Reminder.job_status)
        .all()
    )
    next_retry_at = (
        db.session.query(func.min(Reminder.next_retry_at))
        .filter(
            Reminder.user_id == user_id,
            Reminder.job_status == RETRYING,
            Reminder.next_retry_at.isnot(None),
        )
        .scalar()
    )
    last_failure_at = (
        db.session.query(func.max(Reminder.failed_at))
        .filter(Reminder.user_id == user_id, Reminder.failed_at.isnot(None))
        .scalar()
    )
    return {
        "total": sum(counts.values()),
        "pending": counts.get(PENDING, 0),
        "retrying": counts.get(RETRYING, 0),
        "sent": counts.get(SENT, 0),
        "failed": counts.get(FAILED, 0),
        "due_now": _due_reminders_query(user_id=user_id, now=now).count(),
        "next_retry_at": _iso(next_retry_at),
        "last_failure_at": _iso(last_failure_at),
    }


def reminder_jobs_query(user_id: int, status: str | None = None):
    query = db.session.query(Reminder).filter(Reminder.user_id == user_id)
    if status:
        query = query.filter(Reminder.job_status == status)
    return query.order_by(Reminder.send_at.desc(), Reminder.id.desc())


def _due_reminders_query(user_id: int, now: datetime):
    due_cutoff = now + timedelta(minutes=1)
    return db.session.query(Reminder).filter(
        Reminder.user_id == user_id,
        Reminder.sent.is_(False),
        Reminder.send_at <= due_cutoff,
        Reminder.job_status.in_(ACTIVE_STATUSES),
        or_(Reminder.next_retry_at.is_(None), Reminder.next_retry_at <= now),
    )


def _ensure_retry_defaults(reminder: Reminder) -> None:
    if not reminder.job_status:
        reminder.job_status = PENDING
    if reminder.retry_count is None:
        reminder.retry_count = 0
    if not reminder.max_attempts:
        reminder.max_attempts = configured_max_attempts()


def _delay_for_failure(failure_count: int) -> int:
    delays = configured_retry_delays()
    index = min(max(failure_count - 1, 0), len(delays) - 1)
    return delays[index]


def _truncate_error(error: str | None) -> str:
    text = error or "delivery failed"
    return text[:MAX_ERROR_LENGTH]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
