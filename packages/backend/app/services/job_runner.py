"""
Resilient background job runner for FinMind reminders.

Features:
- Exponential backoff retry (2^n minutes, capped at 60 min)
- Per-reminder failure tracking (retry_count, last_error, failed_permanently)
- JobRun audit log for every execution
- Prometheus counters for sent / retried / permanently-failed reminders
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from ..extensions import db
from ..models import JobRun, Reminder
from ..observability import track_reminder_event
from .reminders import send_reminder

logger = logging.getLogger("finmind.job_runner")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
JOB_REMINDER = "reminder_dispatch"
_MAX_BACKOFF_MINUTES = 60  # cap exponential backoff at 1 hour


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def run_due_reminders(user_id: Optional[int] = None) -> dict:
    """
    Dispatch all due reminders with retry semantics.

    Args:
        user_id: If given, only process reminders for that user (per-user
                 trigger). If None, process across all users (cron mode).

    Returns:
        dict with keys: processed, succeeded, errors, retried, permanently_failed
    """
    started_at = datetime.utcnow()
    job_run = JobRun(
        job_name=JOB_REMINDER,
        started_at=started_at,
        status="running",
    )
    db.session.add(job_run)
    db.session.flush()  # get job_run.id without full commit

    stats = {"processed": 0, "succeeded": 0, "errors": 0, "retried": 0, "permanently_failed": 0}

    try:
        now = datetime.utcnow()
        query = db.session.query(Reminder).filter(
            Reminder.sent.is_(False),
            Reminder.failed_permanently.is_(False),
            db.or_(
                Reminder.next_retry_at.is_(None),
                Reminder.next_retry_at <= now,
            ),
            Reminder.send_at <= now + timedelta(minutes=1),
        )
        if user_id is not None:
            query = query.filter(Reminder.user_id == user_id)

        reminders = query.all()

        for reminder in reminders:
            stats["processed"] += 1

            try:
                ok = send_reminder(reminder)
                if ok:
                    reminder.sent = True
                    reminder.last_error = None
                    stats["succeeded"] += 1
                    track_reminder_event(event="sent", channel=reminder.channel)
                    logger.info(
                        "Reminder sent id=%s user=%s channel=%s retries=%s",
                        reminder.id, reminder.user_id, reminder.channel, reminder.retry_count,
                    )
                else:
                    _handle_failure(reminder, "send_reminder returned False", stats)
            except Exception as exc:  # noqa: BLE001
                _handle_failure(reminder, str(exc), stats)
                logger.exception("Reminder dispatch error id=%s", reminder.id)

        job_status = _derive_status(stats)
        _finalize_job_run(job_run, job_status, stats)
        db.session.commit()

    except Exception:
        logger.exception("Job runner critical failure")
        _finalize_job_run(job_run, "failed", stats)
        db.session.commit()
        raise

    logger.info(
        "Job %s done: processed=%s succeeded=%s errors=%s retried=%s permanently_failed=%s",
        JOB_REMINDER, stats["processed"], stats["succeeded"],
        stats["errors"], stats["retried"], stats["permanently_failed"],
    )
    return stats


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _handle_failure(reminder: Reminder, error_msg: str, stats: dict) -> None:
    """Increment retry counter, schedule next attempt or mark permanently failed."""
    reminder.retry_count += 1
    reminder.last_error = error_msg[:500]
    stats["errors"] += 1

    if reminder.retry_count >= reminder.max_retries:
        reminder.failed_permanently = True
        stats["permanently_failed"] += 1
        track_reminder_event(
            event="failed_permanently",
            channel=reminder.channel,
        )
        logger.warning(
            "Reminder permanently failed id=%s user=%s after %s retries: %s",
            reminder.id, reminder.user_id, reminder.retry_count, error_msg,
        )
    else:
        backoff_minutes = min(
            int(math.pow(2, reminder.retry_count)),
            _MAX_BACKOFF_MINUTES,
        )
        reminder.next_retry_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
        stats['retried'] = stats.get('retried', 0) + 1
        track_reminder_event(
            event="retry_scheduled",
            channel=reminder.channel,
        )
        logger.warning(
            "Reminder will retry id=%s user=%s attempt=%s in %s min: %s",
            reminder.id, reminder.user_id, reminder.retry_count, backoff_minutes, error_msg,
        )


def _derive_status(stats: dict) -> str:
    if stats["processed"] == 0:
        return "no_work"
    if stats["errors"] == 0 and stats["succeeded"] > 0:
        return "success"
    if stats["succeeded"] > 0:
        return "partial"
    return "failed"


def _finalize_job_run(job_run: JobRun, status: str, stats: dict) -> None:
    job_run.finished_at = datetime.utcnow()
    job_run.status = status
    job_run.processed = stats["processed"]
    job_run.succeeded = stats["succeeded"]
    job_run.errors = stats["errors"]
    job_run.retried = stats["retried"]
