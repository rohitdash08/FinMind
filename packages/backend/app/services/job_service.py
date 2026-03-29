"""
Background job retry service with exponential backoff, dead-letter queue, and monitoring.
Implements resilient async job execution for FinMind.
"""
import json
import threading
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from ..extensions import db
from ..models import BackgroundJob, JobStatus


DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_SECONDS = 5
DEFAULT_MAX_DELAY_SECONDS = 300
JOB_LOCK = threading.Lock()


def _calculate_backoff(attempt: int, base_delay: int = DEFAULT_BASE_DELAY_SECONDS,
                       max_delay: int = DEFAULT_MAX_DELAY_SECONDS) -> int:
    """Exponential backoff: min(base * 2^attempt, max)."""
    return int(min(base_delay * (2 ** attempt), max_delay))


def enqueue_job(job_type: str, payload: Dict[str, Any],
                max_retries: int = DEFAULT_MAX_RETRIES,
                user_id: Optional[int] = None) -> BackgroundJob:
    """Create and persist a new background job."""
    job = BackgroundJob(
        job_type=job_type,
        payload=json.dumps(payload),
        status=JobStatus.PENDING.value,
        max_retries=max_retries,
        attempt_count=0,
        user_id=user_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        next_retry_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    return job


def execute_job(job: BackgroundJob, handler: Callable[[Dict], Any]) -> bool:
    """Execute a job with retry logic. Returns True on success."""
    with JOB_LOCK:
        job.status = JobStatus.RUNNING.value
        job.attempt_count += 1
        job.updated_at = datetime.utcnow()
        db.session.commit()

    try:
        payload = json.loads(job.payload or "{}")
        handler(payload)
        with JOB_LOCK:
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.session.commit()
        return True
    except Exception:
        error_msg = f"Attempt {job.attempt_count}: {traceback.format_exc()}"
        with JOB_LOCK:
            existing = job.error_log or ""
            job.error_log = f"{existing}\n---\n{error_msg}".strip()
            if job.attempt_count >= job.max_retries:
                job.status = JobStatus.DEAD.value
            else:
                delay = _calculate_backoff(job.attempt_count)
                job.status = JobStatus.RETRYING.value
                job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
            job.updated_at = datetime.utcnow()
            db.session.commit()
        return False


def get_pending_jobs(limit: int = 50):
    """Return jobs ready for execution."""
    now = datetime.utcnow()
    return BackgroundJob.query.filter(
        BackgroundJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRYING.value]),
        BackgroundJob.next_retry_at <= now,
    ).order_by(BackgroundJob.next_retry_at).limit(limit).all()


def get_dead_letter_jobs(user_id: Optional[int] = None, limit: int = 100):
    """Return jobs in the dead-letter queue."""
    query = BackgroundJob.query.filter_by(status=JobStatus.DEAD.value)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return query.order_by(BackgroundJob.updated_at.desc()).limit(limit).all()


def requeue_dead_job(job_id: int) -> Optional[BackgroundJob]:
    """Manually requeue a dead-letter job."""
    job = BackgroundJob.query.get(job_id)
    if job and job.status == JobStatus.DEAD.value:
        job.status = JobStatus.PENDING.value
        job.attempt_count = 0
        job.error_log = None
        job.next_retry_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.session.commit()
        return job
    return None


def get_job_stats(user_id: Optional[int] = None) -> Dict[str, int]:
    """Return aggregate stats: counts per status."""
    query = BackgroundJob.query
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return {status.value: query.filter_by(status=status.value).count() for status in JobStatus}


def cancel_job(job_id: int) -> bool:
    """Cancel a pending or retrying job."""
    job = BackgroundJob.query.get(job_id)
    if job and job.status in (JobStatus.PENDING.value, JobStatus.RETRYING.value):
        job.status = JobStatus.CANCELLED.value
        job.updated_at = datetime.utcnow()
        db.session.commit()
        return True
    return False
