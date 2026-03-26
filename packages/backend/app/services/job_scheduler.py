"""
Resilient background job scheduler with exponential backoff retry,
circuit breaker pattern, and comprehensive monitoring.
"""

import json
import logging
import random
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable

from ..extensions import db
from ..models import JobExecution, JobStatus, Reminder
from ..services.reminders import send_reminder

logger = logging.getLogger("finmind.jobs")


# ---------------------------------------------------------------------------
# Exponential Backoff Calculator
# ---------------------------------------------------------------------------

def calculate_backoff(retry_count: int, base_seconds: int = 300) -> int:
    """
    Calculate exponential backoff delay with jitter.

    Retry 1: ~5 min (300s)
    Retry 2: ~15 min (900s)
    Retry 3: ~45 min (2700s)

    Jitter of +/- 10% prevents thundering-herd on retries.
    """
    delay = base_seconds * (3 ** retry_count)
    jitter = delay * 0.1
    return int(delay + random.uniform(-jitter, jitter))


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Simple circuit breaker for external service calls.

    States:
    - CLOSED: normal operation, requests go through
    - OPEN: too many failures, requests are rejected immediately
    - HALF_OPEN: allow a single test request after reset_timeout
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 60,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.success_count = 0

    def can_execute(self) -> bool:
        """Check whether a request is allowed through the breaker."""
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if self.last_failure_time and (
                datetime.utcnow() - self.last_failure_time
            ) > timedelta(seconds=self.reset_timeout_seconds):
                self.state = self.HALF_OPEN
                logger.info(
                    "Circuit breaker '%s' transitioning to HALF_OPEN",
                    self.name,
                )
                return True
            return False
        # HALF_OPEN: allow exactly one probe request
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.success_count += 1
        if self.state == self.HALF_OPEN:
            self.state = self.CLOSED
            logger.info(
                "Circuit breaker '%s' closed after successful probe", self.name
            )

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning(
                "Circuit breaker '%s' OPEN after %d consecutive failures",
                self.name,
                self.failure_count,
            )

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "reset_timeout_seconds": self.reset_timeout_seconds,
        }


# Global circuit breakers for external services
email_breaker = CircuitBreaker("email", failure_threshold=5, reset_timeout_seconds=60)
whatsapp_breaker = CircuitBreaker(
    "whatsapp", failure_threshold=3, reset_timeout_seconds=120
)


def get_breaker_for_channel(channel: str) -> CircuitBreaker:
    if "whatsapp" in channel:
        return whatsapp_breaker
    return email_breaker


# ---------------------------------------------------------------------------
# Job Execution Engine
# ---------------------------------------------------------------------------

def create_job(
    job_type: str,
    payload: dict | None = None,
    max_retries: int = 3,
    user_id: int | None = None,
) -> JobExecution:
    """Create a new job execution record."""
    job = JobExecution(
        job_type=job_type,
        status=JobStatus.PENDING.value,
        payload=json.dumps(payload) if payload else None,
        max_retries=max_retries,
        user_id=user_id,
    )
    db.session.add(job)
    db.session.commit()
    logger.info(
        "Created job id=%s type=%s max_retries=%s", job.id, job_type, max_retries
    )
    return job


def execute_job(job: JobExecution, handler: Callable[..., Any]) -> bool:
    """
    Execute a job with retry logic and circuit breaker protection.

    Returns True if the job completed successfully, False otherwise.
    """
    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        payload = json.loads(job.payload) if job.payload else {}

        # Check circuit breaker for channel-based jobs
        channel = payload.get("channel", "email")
        breaker = get_breaker_for_channel(channel)

        if not breaker.can_execute():
            error_msg = (
                f"Circuit breaker '{breaker.name}' is OPEN, "
                f"skipping execution"
            )
            logger.warning(error_msg)
            _schedule_retry(job, error_msg)
            return False

        # Execute the handler
        result = handler(payload)

        # Mark success
        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        job.result = json.dumps({"success": True, "detail": str(result)})
        db.session.commit()
        breaker.record_success()

        logger.info(
            "Job id=%s type=%s completed successfully", job.id, job.job_type
        )
        return True

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        logger.error(
            "Job id=%s type=%s failed: %s\n%s",
            job.id,
            job.job_type,
            error_msg,
            tb,
        )

        # Record failure for circuit breaker
        payload = json.loads(job.payload) if job.payload else {}
        channel = payload.get("channel", "email")
        breaker = get_breaker_for_channel(channel)
        breaker.record_failure()

        _schedule_retry(job, error_msg)
        return False


def _schedule_retry(job: JobExecution, error_msg: str) -> None:
    """Schedule a retry or mark job as dead if max retries exhausted."""
    job.last_error = error_msg
    job.retry_count += 1

    if job.retry_count >= job.max_retries:
        job.status = JobStatus.DEAD.value
        job.completed_at = datetime.utcnow()
        job.result = json.dumps({
            "success": False,
            "detail": f"Exhausted {job.max_retries} retries. Last error: {error_msg}",
        })
        logger.warning(
            "Job id=%s type=%s DEAD after %d retries",
            job.id,
            job.job_type,
            job.max_retries,
        )
    else:
        backoff = calculate_backoff(job.retry_count - 1)
        job.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff)
        job.status = JobStatus.RETRYING.value
        logger.info(
            "Job id=%s type=%s scheduled for retry %d/%d in %ds",
            job.id,
            job.job_type,
            job.retry_count,
            job.max_retries,
            backoff,
        )

    db.session.commit()


def retry_pending_jobs() -> dict:
    """
    Process all jobs that are due for retry.

    Returns a summary dict with counts of processed, succeeded, and failed jobs.
    """
    now = datetime.utcnow()
    retryable = (
        db.session.query(JobExecution)
        .filter(
            JobExecution.status == JobStatus.RETRYING.value,
            JobExecution.next_retry_at <= now,
        )
        .all()
    )

    results = {"processed": 0, "succeeded": 0, "failed": 0}

    for job in retryable:
        results["processed"] += 1
        handler = _get_handler(job.job_type)
        if handler is None:
            logger.error("No handler registered for job type: %s", job.job_type)
            job.status = JobStatus.DEAD.value
            job.last_error = f"No handler for job type: {job.job_type}"
            job.completed_at = datetime.utcnow()
            db.session.commit()
            results["failed"] += 1
            continue

        success = execute_job(job, handler)
        if success:
            results["succeeded"] += 1
        else:
            results["failed"] += 1

    return results


def manually_retry_job(job_id: int) -> JobExecution | None:
    """
    Manually retry a failed or dead job.

    Resets retry count and re-queues the job.
    """
    job = db.session.get(JobExecution, job_id)
    if not job:
        return None

    if job.status not in (JobStatus.FAILED.value, JobStatus.DEAD.value):
        return None

    job.retry_count = 0
    job.status = JobStatus.PENDING.value
    job.next_retry_at = None
    job.last_error = None
    job.result = None
    job.completed_at = None
    db.session.commit()

    handler = _get_handler(job.job_type)
    if handler:
        execute_job(job, handler)

    return job


# ---------------------------------------------------------------------------
# Reminder Job Integration
# ---------------------------------------------------------------------------

def _reminder_job_handler(payload: dict) -> str:
    """Handler for reminder dispatch jobs."""
    reminder_id = payload.get("reminder_id")
    if not reminder_id:
        raise ValueError("reminder_id is required in payload")

    reminder = db.session.get(Reminder, reminder_id)
    if not reminder:
        raise ValueError(f"Reminder {reminder_id} not found")

    if reminder.sent:
        return f"Reminder {reminder_id} already sent, skipping"

    success = send_reminder(reminder)
    if not success:
        raise RuntimeError(
            f"Failed to send reminder {reminder_id} via {reminder.channel}"
        )

    reminder.sent = True
    db.session.commit()
    return f"Reminder {reminder_id} sent successfully via {reminder.channel}"


def dispatch_reminder_with_retry(
    reminder: Reminder, max_retries: int = 3
) -> JobExecution:
    """Create a tracked job for sending a reminder with retry support."""
    return create_job(
        job_type="reminder_dispatch",
        payload={
            "reminder_id": reminder.id,
            "channel": reminder.channel,
            "message_preview": reminder.message[:100],
        },
        max_retries=max_retries,
        user_id=reminder.user_id,
    )


# ---------------------------------------------------------------------------
# Job Handler Registry
# ---------------------------------------------------------------------------

_JOB_HANDLERS: dict[str, Callable] = {
    "reminder_dispatch": _reminder_job_handler,
}


def register_job_handler(job_type: str, handler: Callable) -> None:
    """Register a handler function for a given job type."""
    _JOB_HANDLERS[job_type] = handler


def _get_handler(job_type: str) -> Callable | None:
    return _JOB_HANDLERS.get(job_type)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_job_stats() -> dict:
    """Compute aggregate job execution statistics."""
    from sqlalchemy import func

    total = db.session.query(func.count(JobExecution.id)).scalar() or 0
    by_status = dict(
        db.session.query(JobExecution.status, func.count(JobExecution.id))
        .group_by(JobExecution.status)
        .all()
    )
    by_type = dict(
        db.session.query(JobExecution.job_type, func.count(JobExecution.id))
        .group_by(JobExecution.job_type)
        .all()
    )

    # Average duration for completed jobs
    avg_duration = None
    completed_jobs = (
        db.session.query(JobExecution)
        .filter(
            JobExecution.status == JobStatus.COMPLETED.value,
            JobExecution.started_at.isnot(None),
            JobExecution.completed_at.isnot(None),
        )
        .all()
    )
    if completed_jobs:
        durations = [
            (j.completed_at - j.started_at).total_seconds()
            for j in completed_jobs
        ]
        avg_duration = sum(durations) / len(durations)

    success_count = by_status.get(JobStatus.COMPLETED.value, 0)
    failure_count = by_status.get(JobStatus.DEAD.value, 0)
    success_rate = (
        round(success_count / (success_count + failure_count) * 100, 1)
        if (success_count + failure_count) > 0
        else None
    )

    return {
        "total_jobs": total,
        "by_status": by_status,
        "by_type": by_type,
        "success_rate_percent": success_rate,
        "avg_duration_seconds": round(avg_duration, 3) if avg_duration else None,
        "circuit_breakers": {
            "email": email_breaker.get_status(),
            "whatsapp": whatsapp_breaker.get_status(),
        },
    }
