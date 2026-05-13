"""
Background Job Execution Service

Provides configurable retry logic with exponential backoff
and dead letter queue for failed jobs.

Usage:
    from app.services.jobs import execute_job, get_backoff_delay
    from app.models import JobRecord

    job = JobRecord(job_type="email", args='{"to":"user@example.com"}')
    db.session.add(job)
    db.session.commit()
    execute_job(job, send_email_fn)
"""
import json
import time
import logging
from datetime import datetime
from ..extensions import db
from ..models import JobRecord

logger = logging.getLogger("finmind.jobs")

# Maximum backoff delay in seconds
MAX_BACKOFF_SECONDS = 30


def get_backoff_delay(retry_count: int) -> int:
    """Calculate exponential backoff delay.
    
    Formula: 2^(retry_count + 1) seconds, capped at MAX_BACKOFF_SECONDS.
    
    Args:
        retry_count: Number of retries already attempted.
    
    Returns:
        Delay in seconds before next retry.
    """
    delay = 2 ** (retry_count + 1)
    return min(delay, MAX_BACKOFF_SECONDS)


def execute_job(job: JobRecord, fn, *args, **kwargs):
    """Execute a job function with automatic retry.
    
    The function is called up to job.max_retries times.
    On each failure, waits with exponential backoff before retrying.
    After exhausting retries, the job is moved to dead_letter status.
    
    Args:
        job: JobRecord instance (must be committed to DB).
        fn: Callable to execute.
        *args, **kwargs: Passed to fn.
    
    Returns:
        The return value of fn on success.
    
    Raises:
        RuntimeError: If all retries fail.
    
    State transitions:
        pending → running → completed (on success)
        pending → running → dead_letter (after max retries)
    """
    job.status = "running"
    job.updated_at = datetime.utcnow()
    db.session.commit()

    last_exception = None
    for attempt in range(job.max_retries):
        try:
            result = fn(*args, **kwargs)
            job.status = "completed"
            job.retry_count = attempt
            job.last_error = None
            job.updated_at = datetime.utcnow()
            db.session.commit()
            logger.info("Job %s completed after %d attempt(s)", job.id, attempt + 1)
            return result
        except Exception as e:
            last_exception = str(e)
            job.retry_count = attempt + 1
            job.last_error = last_exception
            job.updated_at = datetime.utcnow()
            db.session.commit()
            logger.warning(
                "Job %s attempt %d failed: %s", job.id, attempt + 1, last_exception
            )
            if attempt < job.max_retries - 1:
                delay = get_backoff_delay(attempt)
                time.sleep(delay)

    job.status = "dead_letter"
    job.updated_at = datetime.utcnow()
    db.session.commit()
    logger.error("Job %s moved to dead_letter after %d retries", job.id, job.max_retries)
    raise RuntimeError(f"Job failed after {job.max_retries} retries: {last_exception}")
