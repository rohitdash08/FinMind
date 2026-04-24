"""
Background job service with retry logic, exponential backoff, and dead-letter queue.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ..extensions import db
from ..models import BackgroundJob, JobStatus

logger = logging.getLogger("finmind.jobs")

# Exponential backoff base (seconds): 30, 120, 480, 1920, ...
BACKOFF_BASE_SECONDS = 30
BACKOFF_MULTIPLIER = 2
MAX_BACKOFF_SECONDS = 3600  # 1 hour cap


def _compute_backoff(attempts: int) -> int:
    """Compute delay in seconds using exponential backoff."""
    delay = BACKOFF_BASE_SECONDS * (BACKOFF_MULTIPLIER ** (attempts - 1))
    return min(delay, MAX_BACKOFF_SECONDS)


def enqueue_job(
    user_id: Optional[int],
    task_type: str,
    payload: Optional[dict] = None,
    max_attempts: int = 3,
    scheduled_for: Optional[datetime] = None,
) -> BackgroundJob:
    """
    Enqueue a new background job.

    Args:
        user_id: Owner of the job (optional for system jobs).
        task_type: Identifier for the job task (e.g., "send_email", "sync_data").
        payload: JSON-serializable data passed to the task handler.
        max_attempts: Maximum number of retry attempts (default 3).
        scheduled_for: Optional scheduled execution time.

    Returns:
        The created BackgroundJob instance.
    """
    job = BackgroundJob(
        user_id=user_id,
        task_type=task_type,
        payload=payload or {},
        status=JobStatus.PENDING,
        max_attempts=max_attempts,
        attempts=0,
        scheduled_for=scheduled_for,
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s user=%s task=%s", job.id, user_id, task_type)
    return job


def get_job(job_id: int, user_id: Optional[int] = None) -> Optional[BackgroundJob]:
    """
    Retrieve a job by ID, optionally filtering by user_id.

    Args:
        job_id: The job ID.
        user_id: If provided, ensures the job belongs to this user.

    Returns:
        BackgroundJob instance or None.
    """
    query = db.session.query(BackgroundJob).filter_by(id=job_id)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return query.first()


def list_jobs(
    user_id: Optional[int] = None,
    status: Optional[JobStatus] = None,
    task_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> list[BackgroundJob]:
    """
    List jobs with optional filters.

    Args:
        user_id: Filter by owner.
        status: Filter by job status.
        task_type: Filter by task type.
        page: Page number (1-indexed).
        page_size: Results per page.

    Returns:
        List of BackgroundJob instances.
    """
    query = db.session.query(BackgroundJob)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if status is not None:
        query = query.filter_by(status=status)
    if task_type is not None:
        query = query.filter_by(task_type=task_type)

    query = query.order_by(BackgroundJob.created_at.desc())
    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size).all()


def mark_running(job: BackgroundJob) -> BackgroundJob:
    """Mark a job as running."""
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Job running id=%s attempt=%s", job.id, job.attempts)
    return job


def mark_succeeded(job: BackgroundJob, result: Optional[dict] = None) -> BackgroundJob:
    """Mark a job as succeeded."""
    job.status = JobStatus.SUCCEEDED
    job.result = result
    job.next_retry_at = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Job succeeded id=%s", job.id)
    return job


def mark_failed(
    job: BackgroundJob,
    error: str,
    move_to_dlq: bool = False,
) -> BackgroundJob:
    """
    Mark a job as failed or schedule retry.

    Args:
        job: The failed job.
        error: Error message to record.
        move_to_dlq: If True, move to dead-letter queue (no more retries).

    Returns:
        Updated BackgroundJob instance.
    """
    job.last_error = error
    job.updated_at = datetime.utcnow()

    if move_to_dlq or job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD
        job.next_retry_at = None
        logger.warning("Job moved to DLQ id=%s reason=%s", job.id, error)
    else:
        # Schedule retry with exponential backoff
        job.status = JobStatus.RETRYING
        delay_seconds = _compute_backoff(job.attempts)
        job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        logger.warning(
            "Job failed, scheduling retry id=%s attempt=%s next=%s",
            job.id,
            job.attempts,
            job.next_retry_at,
        )

    db.session.commit()
    return job


def mark_pending(job: BackgroundJob) -> BackgroundJob:
    """Mark a job as pending (for manual retry)."""
    job.status = JobStatus.PENDING
    job.next_retry_at = None
    job.last_error = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Job marked pending for manual retry id=%s", job.id)
    return job


def get_jobs_due_for_retry(limit: int = 100) -> list[BackgroundJob]:
    """
    Get jobs that are due for retry (RETRYING status with next_retry_at <= now).

    Args:
        limit: Maximum number of jobs to return.

    Returns:
        List of BackgroundJob instances ready for retry.
    """
    now = datetime.utcnow()
    return (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status == JobStatus.RETRYING,
            BackgroundJob.next_retry_at <= now,
        )
        .order_by(BackgroundJob.next_retry_at.asc())
        .limit(limit)
        .all()
    )


def get_pending_jobs(limit: int = 100) -> list[BackgroundJob]:
    """
    Get pending jobs that are ready to execute.

    Args:
        limit: Maximum number of jobs to return.

    Returns:
        List of BackgroundJob instances.
    """
    now = datetime.utcnow()
    return (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status == JobStatus.PENDING,
            db.or_(
                BackgroundJob.scheduled_for.is_(None),
                BackgroundJob.scheduled_for <= now,
            ),
        )
        .order_by(BackgroundJob.created_at.asc())
        .limit(limit)
        .all()
    )


def get_dead_jobs(
    user_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> list[BackgroundJob]:
    """
    Get dead-letter queue jobs.

    Args:
        user_id: Optional filter by user.
        page: Page number.
        page_size: Results per page.

    Returns:
        List of dead BackgroundJob instances.
    """
    query = db.session.query(BackgroundJob).filter_by(status=JobStatus.DEAD)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    offset = (page - 1) * page_size
    return (
        query.order_by(BackgroundJob.updated_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )


def job_to_dict(job: BackgroundJob) -> dict:
    """Serialize a BackgroundJob to a dictionary."""
    return {
        "id": job.id,
        "user_id": job.user_id,
        "task_type": job.task_type,
        "payload": job.payload,
        "status": job.status.value,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
        "result": job.result,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
    }
