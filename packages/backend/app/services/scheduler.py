"""
Scheduler Service for Periodic Tasks

Uses APScheduler to run periodic tasks like weekly digest generation.
"""

import logging
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from .digest import WeeklyDigestService

logger = logging.getLogger("finmind.scheduler")

# Global scheduler instance
scheduler = BackgroundScheduler()


def weekly_digest_job(app: Flask):
    """
    Job function to generate and send weekly digests to all users.

    This runs every Sunday at 9:00 AM UTC by default.
    """
    with app.app_context():
        logger.info("Starting weekly digest generation job")
        try:
            results = WeeklyDigestService.generate_and_send_all_digests()
            logger.info(
                "Weekly digest job completed: %d users, %d digests, %d emails sent",
                results["total_users"],
                results["digests_generated"],
                results["emails_sent"],
            )
            if results["errors"]:
                for error in results["errors"]:
                    logger.error("Digest job error: %s", error)
        except Exception as e:
            logger.exception("Weekly digest job failed: %s", str(e))


def scheduler_event_listener(event):
    """Listen to scheduler events for logging."""
    if event.exception:
        logger.error(
            "Scheduler job %s failed with exception: %s",
            event.job_id,
            event.exception,
        )
    else:
        logger.debug("Scheduler job %s completed successfully", event.job_id)


def init_scheduler(app: Flask):
    """
    Initialize the scheduler with the Flask app.

    Configures weekly digest generation and other periodic tasks.

    Schedule:
        - Weekly digest: Every Sunday at 9:00 AM UTC
    """
    # Add event listener
    scheduler.add_listener(scheduler_event_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Add weekly digest job - runs every Sunday at 9:00 AM UTC
    scheduler.add_job(
        func=weekly_digest_job,
        trigger=CronTrigger(day_of_week="sun", hour=9, minute=0, timezone="UTC"),
        id="weekly_digest",
        name="Weekly Financial Digest",
        args=[app],
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour grace period for misfires
    )

    logger.info(
        "Scheduler initialized with jobs: %s",
        [job.id for job in scheduler.get_jobs()],
    )


def start_scheduler():
    """Start the scheduler if not already running."""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown complete")


def get_scheduler_status():
    """Get the current status of scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return {
        "running": scheduler.running,
        "jobs": jobs,
    }
