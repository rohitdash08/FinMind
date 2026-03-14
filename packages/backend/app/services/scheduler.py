"""
Resilient background job scheduler for FinMind.

Runs reminder dispatch on a 60-second interval with exponential-backoff
retry for failed deliveries (up to MAX_RETRIES attempts).

Retry schedule:
  attempt 1 -> +5 min
  attempt 2 -> +15 min
  attempt 3 -> +45 min
  beyond MAX_RETRIES -> marked failed=True, no further attempts
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore

from ..extensions import db
from ..models import Reminder
from .reminders import send_reminder

logger = logging.getLogger("finmind.scheduler")

MAX_RETRIES = 3
_BACKOFF_MINUTES = [5, 15, 45]

_scheduler: Optional[BackgroundScheduler] = None


def _backoff_delta(retry_count: int) -> timedelta:
    idx = min(retry_count, len(_BACKOFF_MINUTES) - 1)
    return timedelta(minutes=_BACKOFF_MINUTES[idx])


def process_due_reminders(app=None) -> dict:
    """
    Dispatch all due, unsent, non-failed reminders.  Retries reminders
    that previously failed delivery if their next_retry_at has passed.

    Returns a summary dict suitable for logging and the monitoring endpoint.
    """
    ctx = app.app_context() if app else None
    if ctx:
        ctx.push()

    try:
        now = datetime.utcnow() + timedelta(minutes=1)

        pending = (
            db.session.query(Reminder)
            .filter(
                Reminder.sent.is_(False),
                Reminder.failed.is_(False),
                Reminder.send_at <= now,
                db.or_(
                    Reminder.next_retry_at.is_(None),
                    Reminder.next_retry_at <= now,
                ),
            )
            .all()
        )

        sent_count = 0
        retry_count = 0
        failed_count = 0

        for r in pending:
            success = False
            error_msg = None
            try:
                success = send_reminder(r)
                if not success:
                    error_msg = "send_reminder returned False"
            except Exception as exc:  # pragma: no cover
                error_msg = str(exc)

            if success:
                r.sent = True
                r.last_error = None
                sent_count += 1
            else:
                r.retry_count = (r.retry_count or 0) + 1
                r.last_error = error_msg or "unknown error"
                if r.retry_count >= MAX_RETRIES:
                    r.failed = True
                    failed_count += 1
                    logger.warning(
                        "Reminder id=%s permanently failed after %s attempts: %s",
                        r.id,
                        r.retry_count,
                        r.last_error,
                    )
                else:
                    r.next_retry_at = datetime.utcnow() + _backoff_delta(r.retry_count)
                    retry_count += 1
                    logger.info(
                        "Reminder id=%s delivery failed (attempt %s), retry at %s",
                        r.id,
                        r.retry_count,
                        r.next_retry_at.isoformat(),
                    )

        db.session.commit()
        summary = {
            "sent": sent_count,
            "retried": retry_count,
            "permanently_failed": failed_count,
            "total_processed": len(pending),
        }
        if pending:
            logger.info("Reminder job complete: %s", summary)
        return summary

    finally:
        if ctx:
            ctx.pop()


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler


def init_scheduler(app) -> BackgroundScheduler:
    """
    Initialize and start the APScheduler background scheduler.
    Should be called once from create_app(), only in non-testing environments.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    jobstores = {"default": MemoryJobStore()}
    _scheduler = BackgroundScheduler(jobstores=jobstores, timezone="UTC")

    _scheduler.add_job(
        func=process_due_reminders,
        trigger="interval",
        seconds=60,
        id="process_due_reminders",
        name="Dispatch due reminders with retry",
        replace_existing=True,
        kwargs={"app": app},
    )

    _scheduler.start()
    logger.info("Background scheduler started — reminder job interval=60s")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
    _scheduler = None
