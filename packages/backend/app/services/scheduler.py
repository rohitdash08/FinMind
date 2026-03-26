"""APScheduler integration for FinMind background job processing.

Starts a BackgroundScheduler that periodically processes:
  1. Due reminder dispatch
  2. Pending job retries
  3. Health monitoring checks

The scheduler is suppressed in test environments.
"""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("finmind.scheduler")

_scheduler: BackgroundScheduler | None = None


def _is_test_env() -> bool:
    return os.getenv("FLASK_ENV") == "testing" or os.getenv("TESTING") == "1"


def init_scheduler(app) -> BackgroundScheduler | None:
    """Initialize and start the background scheduler.

    Skips initialization in test environments to avoid side effects.
    Returns the scheduler instance, or None in test mode.
    """
    global _scheduler

    if _is_test_env():
        logger.info("Scheduler suppressed in test environment")
        return None

    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)

    # Process due reminder dispatch every 60 seconds
    _scheduler.add_job(
        _dispatch_due_reminders,
        "interval",
        seconds=60,
        id="dispatch_reminders",
        replace_existing=True,
        kwargs={"app": app},
    )

    # Process pending retries every 30 seconds
    _scheduler.add_job(
        _process_retries,
        "interval",
        seconds=30,
        id="process_retries",
        replace_existing=True,
        kwargs={"app": app},
    )

    # Health monitoring every 5 minutes
    _scheduler.add_job(
        _health_check,
        "interval",
        seconds=300,
        id="health_check",
        replace_existing=True,
        kwargs={"app": app},
    )

    _scheduler.start()
    logger.info("Background scheduler started with 3 jobs")
    return _scheduler


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Background scheduler shut down")


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def _dispatch_due_reminders(app) -> None:
    """Find and send all due reminders."""
    from datetime import datetime, timedelta

    from ..extensions import db
    from ..models import Reminder
    from ..services.reminders import send_reminder
    from .job_manager import dispatch_reminders

    with app.app_context():
        try:
            now = datetime.utcnow() + timedelta(minutes=1)
            candidates = (
                db.session.query(Reminder)
                .filter(Reminder.sent.is_(False), Reminder.send_at <= now)
                .all()
            )
            if not candidates:
                return

            result = dispatch_reminders(candidates, send_reminder, now)
            db.session.commit()
            logger.info(
                "Reminder dispatch: sent=%d failed=%d",
                result["sent_count"],
                result["failed_count"],
            )
        except Exception:
            logger.exception("Reminder dispatch failed")
            db.session.rollback()


def _process_retries(app) -> None:
    """Process all pending job retries."""
    from .job_manager import process_pending_retries

    with app.app_context():
        try:
            count = process_pending_retries()
            if count:
                logger.info("Processed %d retries", count)
        except Exception:
            logger.exception("Retry processing failed")


def _health_check(app) -> None:
    """Log job system health status."""
    from .job_manager import get_health_status

    with app.app_context():
        try:
            health = get_health_status()
            if not health["healthy"]:
                logger.warning("Job system unhealthy: %s", health)
            else:
                logger.debug("Job system healthy")
        except Exception:
            logger.exception("Health check failed")
