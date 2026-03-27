import functools
import math
import threading
import time
import logging
from datetime import datetime
from ..extensions import db
from ..models import BackgroundJob, JobStatus

logger = logging.getLogger("finmind.jobs")

_lock = threading.Lock()


def with_retry(name, max_retries=3, base_delay=1.0, backoff_factor=2.0):
    """Decorator that wraps a function as a retryable background job.

    Usage:
        @with_retry("send_email", max_retries=5)
        def send_email(to, subject, body):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            job = BackgroundJob(
                name=name,
                max_retries=max_retries,
                status=JobStatus.PENDING,
            )
            db.session.add(job)
            db.session.commit()

            return _execute_job(job.id, func, args, kwargs, base_delay, backoff_factor)

        return wrapper

    return decorator


def _execute_job(job_id, func, args, kwargs, base_delay, backoff_factor):
    """Execute a job with exponential backoff retry logic."""
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return None

    while job.attempts <= job.max_retries:
        with _lock:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.attempts += 1
            db.session.commit()

        try:
            result = func(*args, **kwargs)
            with _lock:
                job.status = JobStatus.SUCCESS
                job.result = str(result) if result is not None else None
                job.completed_at = datetime.utcnow()
                job.last_error = None
                db.session.commit()

            logger.info(
                "Job succeeded id=%s name=%s attempts=%s",
                job.id, job.name, job.attempts,
            )
            return result

        except Exception as exc:
            error_msg = str(exc)
            with _lock:
                job.last_error = error_msg
                db.session.commit()

            logger.warning(
                "Job failed id=%s name=%s attempt=%s/%s error=%s",
                job.id, job.name, job.attempts, job.max_retries + 1, error_msg,
            )

            if job.attempts > job.max_retries:
                with _lock:
                    job.status = JobStatus.DEAD
                    job.completed_at = datetime.utcnow()
                    db.session.commit()

                logger.error(
                    "Job moved to dead letter id=%s name=%s",
                    job.id, job.name,
                )
                return None

            # Exponential backoff
            delay = base_delay * math.pow(backoff_factor, job.attempts - 1)
            with _lock:
                job.status = JobStatus.RETRYING
                db.session.commit()

            time.sleep(delay)

    return None


def get_job_stats():
    """Get aggregate job statistics."""
    total = db.session.query(BackgroundJob).count()
    by_status = {}
    for status in JobStatus:
        count = (
            db.session.query(BackgroundJob)
            .filter_by(status=status)
            .count()
        )
        by_status[status.value] = count

    success_count = by_status.get("SUCCESS", 0)
    success_rate = round((success_count / total * 100), 2) if total > 0 else 0.0

    return {
        "total": total,
        "by_status": by_status,
        "success_rate": success_rate,
    }


def get_recent_jobs(limit=20):
    """Get recent jobs ordered by creation time."""
    jobs = (
        db.session.query(BackgroundJob)
        .order_by(BackgroundJob.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_job_to_dict(j) for j in jobs]


def get_dead_letter_jobs(limit=50):
    """Get jobs in the dead letter queue."""
    jobs = (
        db.session.query(BackgroundJob)
        .filter_by(status=JobStatus.DEAD)
        .order_by(BackgroundJob.completed_at.desc())
        .limit(limit)
        .all()
    )
    return [_job_to_dict(j) for j in jobs]


def retry_dead_job(job_id, func=None):
    """Retry a dead job by resetting its status."""
    job = db.session.get(BackgroundJob, job_id)
    if not job or job.status != JobStatus.DEAD:
        return None

    job.status = JobStatus.PENDING
    job.attempts = 0
    job.last_error = None
    job.result = None
    job.completed_at = None
    db.session.commit()

    logger.info("Dead job reset for retry id=%s name=%s", job.id, job.name)
    return _job_to_dict(job)


def _job_to_dict(job):
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "attempts": job.attempts,
        "max_retries": job.max_retries,
        "last_error": job.last_error,
        "result": job.result,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    }
