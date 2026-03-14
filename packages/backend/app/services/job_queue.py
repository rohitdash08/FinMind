"""Background job queue with exponential backoff retry and dead letter queue.

Provides an in-process job executor that:
  - Picks up PENDING / retryable jobs and runs registered handlers.
  - Implements exponential back-off (base 2) with jitter.
  - Moves permanently failed jobs to DEAD status (dead letter queue).
  - Exposes helpers for the REST layer to enqueue, retry, and query jobs.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from ..extensions import db
from ..models import BackgroundJob, JobStatus, JobType

logger = logging.getLogger("finmind.jobs")

# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------
JobHandler = Callable[[dict[str, Any]], dict[str, Any] | None]

_handlers: dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    """Register an execution handler for a job type."""
    _handlers[job_type] = handler


# ---------------------------------------------------------------------------
# Job lifecycle helpers
# ---------------------------------------------------------------------------

def enqueue_job(
    *,
    user_id: int,
    name: str,
    job_type: str,
    payload: dict[str, Any] | None = None,
    max_retries: int = 5,
    scheduled_at: datetime | None = None,
) -> BackgroundJob:
    """Create a new background job in PENDING state."""
    if job_type not in {e.value for e in JobType}:
        raise ValueError(f"Unknown job type: {job_type}")

    job = BackgroundJob(
        user_id=user_id,
        name=name,
        job_type=job_type,
        status=JobStatus.PENDING.value,
        payload=json.dumps(payload) if payload else None,
        max_retries=max_retries,
        scheduled_at=scheduled_at or datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s type=%s user=%s", job.id, job_type, user_id)
    return job


def _compute_next_retry(attempts: int) -> datetime:
    """Exponential back-off: 2^attempts seconds + uniform jitter [0, 2s]."""
    delay = (2 ** attempts) + random.uniform(0, 2)  # noqa: S311
    return datetime.utcnow() + timedelta(seconds=delay)


def execute_job(job: BackgroundJob) -> None:
    """Run a single job through its registered handler."""
    handler = _handlers.get(job.job_type)
    if handler is None:
        job.status = JobStatus.DEAD.value
        job.last_error = f"No handler registered for job type: {job.job_type}"
        db.session.commit()
        logger.error("No handler for job id=%s type=%s", job.id, job.job_type)
        return

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    job.attempts += 1
    db.session.commit()

    try:
        payload = json.loads(job.payload) if job.payload else {}
        result = handler(payload)
        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        job.result = json.dumps(result) if result else None
        job.last_error = None
        db.session.commit()
        logger.info(
            "Job id=%s completed on attempt %s", job.id, job.attempts
        )
    except Exception as exc:
        job.last_error = str(exc)
        if job.attempts >= job.max_retries:
            # Move to dead letter queue
            job.status = JobStatus.DEAD.value
            logger.warning(
                "Job id=%s moved to dead letter queue after %s attempts: %s",
                job.id,
                job.attempts,
                exc,
            )
        else:
            job.status = JobStatus.FAILED.value
            job.next_retry_at = _compute_next_retry(job.attempts)
            logger.info(
                "Job id=%s failed (attempt %s/%s), retry at %s: %s",
                job.id,
                job.attempts,
                job.max_retries,
                job.next_retry_at,
                exc,
            )
        db.session.commit()


def retry_job(job: BackgroundJob) -> BackgroundJob:
    """Manually re-queue a FAILED or DEAD job for immediate retry."""
    if job.status not in (JobStatus.FAILED.value, JobStatus.DEAD.value):
        raise ValueError(
            f"Cannot retry job in status {job.status}; only FAILED or DEAD jobs can be retried"
        )
    job.status = JobStatus.PENDING.value
    job.next_retry_at = None
    # Keep current attempts count so history is preserved
    db.session.commit()
    logger.info("Manually retried job id=%s", job.id)
    return job


# ---------------------------------------------------------------------------
# Built-in job handlers (pluggable stubs with real structure)
# ---------------------------------------------------------------------------

def _handle_data_sync(payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronise financial data from external sources."""
    logger.info("Running data sync with payload: %s", payload)
    source = payload.get("source", "bank_api")
    # In production this would call external APIs. Simulate work:
    time.sleep(0.05)
    return {"source": source, "records_synced": 0, "status": "ok"}


def _handle_report_generation(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a financial report (expense summary, analytics, etc.)."""
    logger.info("Generating report with payload: %s", payload)
    report_type = payload.get("report_type", "monthly_summary")
    time.sleep(0.05)
    return {"report_type": report_type, "status": "generated"}


def _handle_email_notification(payload: dict[str, Any]) -> dict[str, Any]:
    """Send an email notification (bill due, budget alert, etc.)."""
    logger.info("Sending email notification with payload: %s", payload)
    recipient = payload.get("recipient", "user")
    subject = payload.get("subject", "FinMind Notification")
    time.sleep(0.05)
    return {"recipient": recipient, "subject": subject, "status": "sent"}


# Register built-in handlers
register_handler(JobType.DATA_SYNC.value, _handle_data_sync)
register_handler(JobType.REPORT_GENERATION.value, _handle_report_generation)
register_handler(JobType.EMAIL_NOTIFICATION.value, _handle_email_notification)


# ---------------------------------------------------------------------------
# Background worker thread (process pending & retryable jobs)
# ---------------------------------------------------------------------------

class JobWorker:
    """Lightweight background worker that polls for runnable jobs."""

    def __init__(self, app, interval: float = 5.0) -> None:
        self._app = app
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Job worker started (interval=%ss)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Job worker stopped")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._app.app_context():
                    self._process_pending()
            except Exception:
                logger.exception("Job worker iteration failed")
            self._stop_event.wait(self._interval)

    def _process_pending(self) -> None:
        now = datetime.utcnow()
        jobs = (
            db.session.query(BackgroundJob)
            .filter(
                BackgroundJob.status.in_(
                    [JobStatus.PENDING.value, JobStatus.FAILED.value]
                ),
                db.or_(
                    BackgroundJob.scheduled_at <= now,
                    BackgroundJob.scheduled_at.is_(None),
                ),
                db.or_(
                    BackgroundJob.next_retry_at <= now,
                    BackgroundJob.next_retry_at.is_(None),
                ),
            )
            .order_by(BackgroundJob.created_at)
            .limit(10)
            .all()
        )
        for job in jobs:
            execute_job(job)
