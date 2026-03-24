"""Resilient background job execution engine with retry and dead-letter support.

Implements exponential backoff retries, job lifecycle tracking, and dead-letter
queue for permanently failed jobs. Integrates with Prometheus metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.exc import OperationalError

from ..extensions import db
from ..models import BackgroundJob, JobStatus

logger = logging.getLogger("finmind.jobs")

# Exponential backoff: 30s, 2min, 8min
BACKOFF_BASE_SECONDS = 30
BACKOFF_MULTIPLIER = 4

# Registry of job type handlers
_job_handlers: dict[str, Callable] = {}


def register_handler(job_type: str):
    """Decorator to register a handler function for a job type.

    Usage:
        @register_handler("send_reminder")
        def handle_send_reminder(payload: dict) -> dict:
            ...
            return {"result": "sent"}
    """

    def decorator(fn: Callable) -> Callable:
        _job_handlers[job_type] = fn
        return fn

    return decorator


def enqueue(
    job_type: str,
    payload: dict[str, Any] | None = None,
    max_retries: int = 3,
    delay_seconds: int = 0,
) -> BackgroundJob:
    """Create a new background job and enqueue it for processing.

    Args:
        job_type: Identifier for the job handler to use.
        payload: JSON-serializable data passed to the handler.
        max_retries: Maximum retry attempts before dead-letter.
        delay_seconds: Seconds to wait before first execution.

    Returns:
        The created BackgroundJob instance.
    """
    now = datetime.utcnow()
    job = BackgroundJob(
        job_type=job_type,
        payload=payload or {},
        status=JobStatus.PENDING,
        attempt=0,
        max_retries=max_retries,
        next_run_at=now + timedelta(seconds=delay_seconds),
    )
    db.session.add(job)
    db.session.commit()
    logger.info(
        "Enqueued job id=%s type=%s max_retries=%s delay=%ss",
        job.id,
        job_type,
        max_retries,
        delay_seconds,
    )
    _track_job_event("enqueued", job_type)
    return job


def calculate_backoff(attempt: int) -> timedelta:
    """Calculate exponential backoff delay for a given attempt number.

    Attempt 1 -> 30s, Attempt 2 -> 2min, Attempt 3 -> 8min, etc.
    """
    seconds = BACKOFF_BASE_SECONDS * (BACKOFF_MULTIPLIER ** (attempt - 1))
    return timedelta(seconds=seconds)


def execute_job(job: BackgroundJob) -> bool:
    """Execute a single background job.

    Runs the registered handler for the job type. On success, marks the job as
    SUCCESS. On failure, either schedules a retry (with backoff) or moves the
    job to DEAD_LETTER if max retries exhausted.

    Args:
        job: The BackgroundJob to execute.

    Returns:
        True if the job succeeded, False otherwise.
    """
    handler = _job_handlers.get(job.job_type)
    if handler is None:
        logger.error("No handler registered for job_type=%s", job.job_type)
        job.status = JobStatus.FAILED
        job.last_error = f"No handler registered for job type: {job.job_type}"
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _track_job_event("failed", job.job_type, reason="no_handler")
        return False

    job.status = JobStatus.RUNNING
    job.attempt += 1
    job.updated_at = datetime.utcnow()
    db.session.commit()

    logger.info(
        "Executing job id=%s type=%s attempt=%s/%s",
        job.id,
        job.job_type,
        job.attempt,
        job.max_retries,
    )

    try:
        result = handler(job.payload)
        job.status = JobStatus.SUCCESS
        job.result = result if isinstance(result, dict) else {"value": str(result)}
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info("Job id=%s succeeded on attempt=%s", job.id, job.attempt)
        _track_job_event("succeeded", job.job_type)
        return True

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Job id=%s failed on attempt=%s/%s: %s",
            job.id,
            job.attempt,
            job.max_retries,
            error_msg,
        )
        job.last_error = error_msg
        job.updated_at = datetime.utcnow()

        if job.attempt >= job.max_retries:
            job.status = JobStatus.DEAD_LETTER
            job.completed_at = datetime.utcnow()
            logger.error(
                "Job id=%s moved to DEAD_LETTER after %s attempts",
                job.id,
                job.attempt,
            )
            _track_job_event("dead_lettered", job.job_type)
        else:
            backoff = calculate_backoff(job.attempt)
            job.status = JobStatus.PENDING
            job.next_run_at = datetime.utcnow() + backoff
            logger.info(
                "Job id=%s scheduled for retry in %s (attempt %s/%s)",
                job.id,
                backoff,
                job.attempt + 1,
                job.max_retries,
            )
            _track_job_event("retried", job.job_type)

        db.session.commit()
        return False


def process_due_jobs(limit: int = 50) -> dict[str, int]:
    """Process all jobs that are due for execution.

    Finds PENDING jobs where next_run_at <= now, executes them, and returns
    a summary of results.

    Args:
        limit: Maximum number of jobs to process in one batch.

    Returns:
        Dict with counts: {"processed": N, "succeeded": N, "failed": N, "dead_lettered": N}
    """
    now = datetime.utcnow()
    due_jobs = (
        BackgroundJob.query.filter(
            BackgroundJob.status == JobStatus.PENDING,
            BackgroundJob.next_run_at <= now,
        )
        .order_by(BackgroundJob.next_run_at)
        .limit(limit)
        .all()
    )

    stats = {"processed": 0, "succeeded": 0, "failed": 0, "dead_lettered": 0}

    for job in due_jobs:
        stats["processed"] += 1
        # Re-fetch to avoid stale data in batch processing
        db.session.refresh(job)
        if job.status != JobStatus.PENDING:
            continue

        success = execute_job(job)
        if success:
            stats["succeeded"] += 1
        elif job.status == JobStatus.DEAD_LETTER:
            stats["dead_lettered"] += 1
        else:
            stats["failed"] += 1

    if stats["processed"] > 0:
        logger.info("Job batch complete: %s", stats)

    return stats


def retry_dead_letter_job(job_id: int) -> bool:
    """Manually retry a dead-lettered job.

    Resets the job to PENDING with attempt=0 and immediate next_run_at.

    Args:
        job_id: ID of the dead-lettered job.

    Returns:
        True if the job was reset, False if not found or not in DEAD_LETTER.
    """
    job = db.session.get(BackgroundJob, job_id)
    if not job or job.status != JobStatus.DEAD_LETTER:
        return False

    job.status = JobStatus.PENDING
    job.attempt = 0
    job.last_error = None
    job.next_run_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    job.completed_at = None
    db.session.commit()
    logger.info("Dead-letter job id=%s reset to PENDING for manual retry", job_id)
    _track_job_event("manual_retry", job.job_type)
    return True


def get_job_stats() -> dict[str, Any]:
    """Get aggregated job statistics for monitoring.

    Returns:
        Dict with counts by status and per-type breakdown.
    """
    from sqlalchemy import func

    status_counts = dict(
        db.session.query(BackgroundJob.status, func.count(BackgroundJob.id))
        .group_by(BackgroundJob.status)
        .all()
    )

    type_counts = dict(
        db.session.query(BackgroundJob.job_type, func.count(BackgroundJob.id))
        .group_by(BackgroundJob.job_type)
        .all()
    )

    # Convert enum keys to strings
    status_counts_str = {str(k): v for k, v in status_counts.items()}

    return {
        "by_status": status_counts_str,
        "by_type": type_counts,
        "total": sum(status_counts.values()),
    }


def _track_job_event(event: str, job_type: str, reason: str = "ok") -> None:
    """Record a job event to Prometheus metrics if observability is available."""
    try:
        from flask import current_app, has_request_context

        if has_request_context():
            obs = current_app.extensions.get("observability")
            if obs:
                obs.record_job_event(event=event, job_type=job_type, status=reason)
    except Exception:
        pass  # Observability is best-effort
