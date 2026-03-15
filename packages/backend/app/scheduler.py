"""
APScheduler integration for FinMind background processing.

Initializes a BackgroundScheduler that periodically runs
``process_due_reminders`` without requiring any user interaction.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger("finmind.scheduler")


def init_scheduler(app: Flask) -> None:
    """
    Start the background scheduler unless we're in testing mode.

    The scheduler is stored on ``app.extensions["scheduler"]`` and
    can be paused / resumed via the admin API.
    """
    # Never start the scheduler during tests or CLI commands
    if app.config.get("TESTING") or os.getenv("FLASK_ENV") == "testing":
        logger.info("Scheduler disabled in testing mode")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:  # pragma: no cover
        logger.warning("APScheduler not installed — background jobs disabled")
        return

    interval_seconds = int(os.getenv("JOB_INTERVAL_SECONDS", "60"))
    batch_size = int(os.getenv("JOB_BATCH_SIZE", "50"))

    scheduler = BackgroundScheduler(daemon=True)

    def _run_job():
        """Execute reminder processing within app context."""
        with app.app_context():
            from .services.job_runner import process_due_reminders
            try:
                process_due_reminders(batch_size=batch_size)
            except Exception:
                logger.exception("Background job run failed")

    scheduler.add_job(
        _run_job,
        trigger="interval",
        seconds=interval_seconds,
        id="process_due_reminders",
        name="Process due reminders",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    app.extensions["scheduler"] = scheduler
    logger.info(
        "Background scheduler started (interval=%ds, batch=%d)",
        interval_seconds,
        batch_size,
    )

    # Graceful shutdown
    atexit.register(lambda: _shutdown(scheduler))


def _shutdown(scheduler) -> None:
    """Shut down the scheduler without waiting for running jobs."""
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Background scheduler stopped")
    except Exception:
        pass
