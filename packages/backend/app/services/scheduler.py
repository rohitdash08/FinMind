"""
Resilient background job scheduler with exponential backoff retry.

Retry intervals: 5 min → 15 min → 45 min (max 3 attempts).
After 3 failures a reminder is permanently marked failed=True.

Design note:
  The core retry logic lives in ``dispatch_reminders()`` which accepts
  candidates and a sender callable — this keeps it fully unit-testable
  without a real database, scheduler, or Flask app context.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger("finmind.scheduler")

# Exponential backoff delays in minutes
_RETRY_DELAYS: list[int] = [5, 15, 45]
MAX_RETRIES: int = len(_RETRY_DELAYS)

_scheduler: BackgroundScheduler | None = None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def backoff_delta(retry_count: int) -> timedelta:
    """Return the wait timedelta before the next attempt.

    ``retry_count`` is the number of attempts *already made* (0-based).
    Values beyond the table are capped at the last entry.

    >>> backoff_delta(0) == timedelta(minutes=5)
    True
    >>> backoff_delta(1) == timedelta(minutes=15)
    True
    >>> backoff_delta(2) == timedelta(minutes=45)
    True
    >>> backoff_delta(99) == timedelta(minutes=45)  # capped
    True
    """
    idx = min(retry_count, len(_RETRY_DELAYS) - 1)
    return timedelta(minutes=_RETRY_DELAYS[idx])


# ---------------------------------------------------------------------------
# Pure dispatch logic — testable without Flask / DB / scheduler
# ---------------------------------------------------------------------------

def dispatch_reminders(
    candidates: list,
    sender: Callable,
    now: datetime | None = None,
) -> dict:
    """Process a list of reminder objects and apply exponential backoff.

    Parameters
    ----------
    candidates:
        Reminder ORM objects (or any object with the expected attributes).
    sender:
        Callable that receives a reminder and returns ``True`` on success.
    now:
        Current UTC time; defaults to ``datetime.utcnow()``.

    Returns
    -------
    dict with keys: dispatched, retried, failed_permanently, skipped.
    """
    if now is None:
        now = datetime.utcnow()

    summary: dict[str, int] = {
        "dispatched": 0,
        "retried": 0,
        "failed_permanently": 0,
        "skipped": 0,
    }

    for reminder in candidates:
        # Skip if not yet due for the initial send
        if reminder.send_at > now and reminder.retry_count == 0:
            summary["skipped"] += 1
            continue

        # Skip if still inside a retry back-off window
        if reminder.next_retry_at is not None and reminder.next_retry_at > now:
            summary["skipped"] += 1
            continue

        # Attempt delivery
        ok = False
        try:
            ok = sender(reminder)
        except Exception as exc:
            logger.exception("sender raised for reminder id=%s", reminder.id)
            reminder.last_error = str(exc)[:500]
        else:
            if not ok:
                reminder.last_error = "sender returned False"

        if ok:
            reminder.sent = True
            reminder.last_error = None
            reminder.retry_status = "sent"
            if reminder.retry_count > 0:
                summary["retried"] += 1
            else:
                summary["dispatched"] += 1
            logger.info(
                "Reminder id=%s dispatched (attempt=%s)",
                reminder.id,
                reminder.retry_count,
            )
        else:
            reminder.retry_count = (reminder.retry_count or 0) + 1
            reminder.last_retry_at = now

            if reminder.retry_count >= MAX_RETRIES:
                reminder.failed = True
                reminder.retry_status = "failed"
                summary["failed_permanently"] += 1
                logger.warning(
                    "Reminder id=%s permanently failed after %s attempts",
                    reminder.id,
                    reminder.retry_count,
                )
            else:
                delta = backoff_delta(reminder.retry_count - 1)
                reminder.next_retry_at = now + delta
                reminder.retry_status = "retrying"
                summary["retried"] += 1
                logger.info(
                    "Reminder id=%s retry %s/%s in %s",
                    reminder.id,
                    reminder.retry_count,
                    MAX_RETRIES,
                    delta,
                )

    return summary


# ---------------------------------------------------------------------------
# Flask-aware wrapper (imports db / Reminder inside app context)
# ---------------------------------------------------------------------------

def process_due_reminders(app) -> dict:
    """Process due reminders inside a Flask app context.

    Fetches candidates from the database, dispatches them, commits changes,
    and returns a summary dict.
    """
    from ..extensions import db
    from ..models import Reminder
    from .reminders import send_reminder

    with app.app_context():
        candidates = (
            db.session.query(Reminder)
            .filter(
                Reminder.sent.is_(False),
                Reminder.failed.is_(False),
            )
            .all()
        )

        summary = dispatch_reminders(candidates, send_reminder)
        db.session.commit()

    logger.info("process_due_reminders summary: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def build_scheduler(app) -> BackgroundScheduler | None:
    """Create and start the APScheduler background scheduler.

    Returns ``None`` when running under a test environment so unit tests are
    not affected by background threads.
    """
    if os.getenv("FLASK_ENV") == "testing" or app.config.get("TESTING"):
        logger.info("Scheduler disabled in test environment")
        return None

    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    jobstores = {"default": MemoryJobStore()}
    executors = {"default": ThreadPoolExecutor(max_workers=2)}
    job_defaults = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}

    _scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone="UTC",
    )

    _scheduler.add_job(
        _process_due_reminders_job,
        trigger="interval",
        seconds=60,
        id="process_due_reminders",
        name="Process due reminders with retry",
        replace_existing=True,
        args=[app],
    )

    _scheduler.start()
    logger.info("Scheduler started — process_due_reminders fires every 60 s")
    return _scheduler


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def _process_due_reminders_job(app) -> None:
    """Wrapper that keeps the scheduler alive even if the job raises."""
    try:
        process_due_reminders(app)
    except Exception:
        logger.exception("Unhandled error in process_due_reminders job")
