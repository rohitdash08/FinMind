"""Background job dispatch logic with exponential backoff retry."""
from datetime import datetime, timedelta
import logging
import os

from ..extensions import db
from ..models import Reminder
from .reminders import send_reminder

logger = logging.getLogger("finmind.jobs")

MAX_RETRIES = int(os.environ.get("JOB_MAX_RETRIES", 3))
RETRY_DELAYS_MINUTES = [
    int(x) for x in os.environ.get("JOB_RETRY_DELAYS", "5,15,45").split(",")
]


def _due_reminders():
    """Return reminders that are due for initial send or a scheduled retry."""
    now = datetime.utcnow()
    return (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.failed.is_(False),
            db.or_(
                db.and_(Reminder.retry_count == 0, Reminder.send_at <= now),
                db.and_(Reminder.retry_count > 0, Reminder.next_retry_at <= now),
            ),
        )
        .all()
    )


def dispatch_reminders() -> dict:
    """Process all due reminders; apply exponential backoff on failure.

    Must be called within an active Flask application context.

    Returns a dict with counts: processed, sent, retrying, failed.
    """
    now = datetime.utcnow()
    reminders = _due_reminders()

    counts = {"processed": 0, "sent": 0, "retrying": 0, "failed": 0}

    for r in reminders:
        counts["processed"] += 1
        try:
            success = send_reminder(r)
        except Exception as exc:
            success = False
            r.last_error = str(exc)[:500]

        if success:
            r.sent = True
            r.retry_status = "sent"
            counts["sent"] += 1
            logger.info("Reminder sent id=%s channel=%s", r.id, r.channel)
        else:
            new_count = r.retry_count + 1
            r.retry_count = new_count
            if not r.last_error:
                r.last_error = "send_reminder returned False"

            if new_count > MAX_RETRIES:
                r.failed = True
                r.retry_status = "failed"
                counts["failed"] += 1
                logger.warning(
                    "Reminder permanently failed id=%s retries=%s error=%s",
                    r.id,
                    new_count,
                    r.last_error,
                )
            else:
                delay = RETRY_DELAYS_MINUTES[new_count - 1]
                r.next_retry_at = now + timedelta(minutes=delay)
                r.retry_status = "retrying"
                counts["retrying"] += 1
                logger.info(
                    "Reminder retry scheduled id=%s attempt=%s next_in=%dmin",
                    r.id,
                    new_count,
                    delay,
                )

    db.session.commit()
    logger.info("dispatch_reminders complete counts=%s", counts)
    return counts


def reminder_stats() -> dict:
    """Return aggregate counts for the reminders table."""
    total = db.session.query(Reminder).count()
    pending = (
        db.session.query(Reminder)
        .filter(Reminder.sent.is_(False), Reminder.failed.is_(False), Reminder.retry_count == 0)
        .count()
    )
    sent = db.session.query(Reminder).filter(Reminder.sent.is_(True)).count()
    failed = db.session.query(Reminder).filter(Reminder.failed.is_(True)).count()
    retrying = (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.failed.is_(False),
            Reminder.retry_count > 0,
        )
        .count()
    )
    return {
        "total": total,
        "pending": pending,
        "sent": sent,
        "retrying": retrying,
        "failed": failed,
    }
