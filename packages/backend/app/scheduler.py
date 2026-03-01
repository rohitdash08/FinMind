"""APScheduler jobs for FinMind – includes the weekly digest delivery."""

import logging
from apscheduler.schedulers.background import BackgroundScheduler

from .extensions import db
from .models import User
from .services.digest import generate_weekly_digest, format_digest_text
from .services.reminders import send_email

logger = logging.getLogger("finmind.scheduler")
_scheduler: BackgroundScheduler | None = None


def _send_weekly_digests(app):
    """Job callback: generate and email digest to every user."""
    with app.app_context():
        users = db.session.query(User).all()
        for user in users:
            try:
                digest = generate_weekly_digest(user.id)
                text = format_digest_text(digest)
                send_email(user.email, "Your FinMind Weekly Digest", text)
                logger.info("Weekly digest sent to user=%s", user.id)
            except Exception:
                logger.exception("Failed to send digest to user=%s", user.id)


def init_scheduler(app):
    """Start the background scheduler with the weekly digest job.

    Runs every Monday at 08:00 UTC.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _send_weekly_digests,
        trigger="cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        args=[app],
        id="weekly_digest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started – weekly digest job registered (Mon 08:00 UTC)")
    return _scheduler
