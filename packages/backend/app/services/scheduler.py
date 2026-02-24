"""
scheduler.py — APScheduler-based background job service.

Jobs:
  send_pending_reminders()  — runs every 5 minutes
  retry_failed_reminders()  — runs every 15 minutes

Usage:
  scheduler = build_scheduler(app)   # call from create_app()
  scheduler.start()
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_ERROR

logger = logging.getLogger("finmind.scheduler")

_MAX_RETRIES = 3


def _send_pending_reminders(app):
    """
    Find all unsent reminders whose send_at has passed and attempt delivery.
    Marks each reminder as sent on success.
    """
    from ..extensions import db
    from ..models import JobExecutionLog, JobStatus, Reminder
    from ..services.reminders import send_reminder

    with app.app_context():
        started = datetime.utcnow()
        job_log = JobExecutionLog(job_name="send_pending_reminders", started_at=started)
        db.session.add(job_log)
        db.session.commit()
        job_id = job_log.id

        processed = failed = 0
        status = JobStatus.SUCCESS.value
        try:
            now = datetime.utcnow()
            pending = (
                db.session.query(Reminder)
                .filter(Reminder.sent == False, Reminder.send_at <= now)  # noqa: E712
                .order_by(Reminder.send_at.asc())
                .limit(100)   # safety cap per run
                .all()
            )
            logger.info("send_pending_reminders: found %d due reminders", len(pending))
            for r in pending:
                ok = send_reminder(r)
                if ok:
                    r.sent = True
                    processed += 1
                else:
                    failed += 1
            db.session.commit()
            status = JobStatus.SUCCESS.value if failed == 0 else JobStatus.PARTIAL.value
        except Exception as exc:
            logger.exception("send_pending_reminders failed: %s", exc)
            status = JobStatus.FAILED.value
            failed += 1

        # Update log
        log = db.session.get(JobExecutionLog, job_id)
        if log:
            log.finished_at = datetime.utcnow()
            log.status = status
            log.records_processed = processed
            log.records_failed = failed
            db.session.commit()

        logger.info(
            "send_pending_reminders done: processed=%d failed=%d status=%s",
            processed, failed, status,
        )


def _retry_failed_reminders(app):
    """
    Find reminders that failed delivery (ReminderDeliveryLog.success=False)
    and haven't exceeded _MAX_RETRIES. Re-attempt delivery.
    """
    from sqlalchemy import func
    from ..extensions import db
    from ..models import JobExecutionLog, JobStatus, Reminder, ReminderDeliveryLog
    from ..services.reminders import send_reminder

    with app.app_context():
        started = datetime.utcnow()
        job_log = JobExecutionLog(job_name="retry_failed_reminders", started_at=started)
        db.session.add(job_log)
        db.session.commit()
        job_id = job_log.id

        processed = failed = 0
        status = JobStatus.SUCCESS.value
        try:
            # Find reminders with at least one failure within 24h window
            retry_window = datetime.utcnow() - timedelta(hours=24)
            failed_ids = (
                db.session.query(ReminderDeliveryLog.reminder_id)
                .filter(
                    ReminderDeliveryLog.success == False,  # noqa: E712
                    ReminderDeliveryLog.attempted_at >= retry_window,
                )
                .distinct()
                .all()
            )
            failed_reminder_ids = [r.reminder_id for r in failed_ids]

            if not failed_reminder_ids:
                status = JobStatus.SUCCESS.value
            else:
                retryable = []
                for rid in failed_reminder_ids:
                    attempt_count = (
                        db.session.query(func.count(ReminderDeliveryLog.id))
                        .filter(ReminderDeliveryLog.reminder_id == rid)
                        .scalar()
                    ) or 0
                    if attempt_count < _MAX_RETRIES:
                        r = db.session.get(Reminder, rid)
                        if r and not r.sent:
                            retryable.append(r)

                logger.info("retry_failed_reminders: %d eligible for retry", len(retryable))
                for r in retryable:
                    ok = send_reminder(r)
                    if ok:
                        r.sent = True
                        processed += 1
                    else:
                        failed += 1
                db.session.commit()
                status = JobStatus.SUCCESS.value if failed == 0 else JobStatus.PARTIAL.value

        except Exception as exc:
            logger.exception("retry_failed_reminders failed: %s", exc)
            status = JobStatus.FAILED.value

        log = db.session.get(JobExecutionLog, job_id)
        if log:
            log.finished_at = datetime.utcnow()
            log.status = status
            log.records_processed = processed
            log.records_failed = failed
            db.session.commit()

        logger.info(
            "retry_failed_reminders done: processed=%d failed=%d status=%s",
            processed, failed, status,
        )


def build_scheduler(app) -> BackgroundScheduler:
    """
    Create and configure the APScheduler BackgroundScheduler.
    Call scheduler.start() after building.
    """
    executors = {"default": ThreadPoolExecutor(max_workers=2)}
    job_defaults = {
        "coalesce": True,           # merge missed runs into one
        "max_instances": 1,         # prevent overlap
        "misfire_grace_time": 300,  # allow up to 5min late start
    }

    scheduler = BackgroundScheduler(
        executors=executors,
        job_defaults=job_defaults,
        timezone="UTC",
    )

    # Job 1: Send pending reminders every 5 minutes
    scheduler.add_job(
        func=_send_pending_reminders,
        args=[app],
        trigger="interval",
        minutes=5,
        id="send_pending_reminders",
        name="Send pending reminder notifications",
        replace_existing=True,
    )

    # Job 2: Retry failed reminders every 15 minutes
    scheduler.add_job(
        func=_retry_failed_reminders,
        args=[app],
        trigger="interval",
        minutes=15,
        id="retry_failed_reminders",
        name="Retry failed reminder deliveries",
        replace_existing=True,
    )

    def _on_job_error(event):
        logger.error(
            "Scheduler job %s raised an unhandled exception: %s",
            event.job_id,
            event.exception,
        )

    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
    return scheduler
