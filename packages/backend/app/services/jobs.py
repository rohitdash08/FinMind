from datetime import datetime, timedelta
import logging
import traceback

from ..extensions import db
from ..models import BackgroundJob, JobExecutionLog, JobStatus

logger = logging.getLogger("finmind.jobs")

# Base delay in seconds for exponential backoff (5^attempt: 5, 25, 125 …)
BACKOFF_BASE = 5

# Registry of callable handlers keyed by job_type string.
_handlers: dict[str, callable] = {}


def register_handler(job_type: str):
    """Decorator to register a handler function for a given job_type."""

    def decorator(fn):
        _handlers[job_type] = fn
        return fn

    return decorator


def get_handler(job_type: str):
    return _handlers.get(job_type)


def create_job(job_type: str, payload: dict | None = None, max_retries: int = 3):
    """Enqueue a new background job and return it."""
    job = BackgroundJob(
        job_type=job_type,
        payload=payload,
        max_retries=max_retries,
        status=JobStatus.PENDING.value,
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Created job id=%s type=%s", job.id, job_type)
    return job


def execute_job(job: BackgroundJob) -> BackgroundJob:
    """Execute a single job, handling retries and logging each attempt."""
    handler = get_handler(job.job_type)
    if handler is None:
        job.status = JobStatus.FAILED.value
        job.last_error = f"No handler registered for job_type={job.job_type}"
        db.session.commit()
        logger.error("No handler for job id=%s type=%s", job.id, job.job_type)
        return job

    job.status = JobStatus.RUNNING.value
    db.session.commit()

    attempt = job.retry_count + 1
    started_at = datetime.utcnow()
    log_entry = JobExecutionLog(
        job_id=job.id,
        attempt=attempt,
        status=JobStatus.RUNNING.value,
        started_at=started_at,
    )
    db.session.add(log_entry)
    db.session.commit()

    try:
        result = handler(job.payload)
        finished_at = datetime.utcnow()

        job.status = JobStatus.COMPLETED.value
        job.result = result if isinstance(result, dict) else {"ok": True}
        job.last_error = None
        job.next_retry_at = None
        job.updated_at = finished_at

        log_entry.status = JobStatus.COMPLETED.value
        log_entry.finished_at = finished_at

        db.session.commit()
        logger.info("Job id=%s completed on attempt %s", job.id, attempt)

    except Exception as exc:
        finished_at = datetime.utcnow()
        error_msg = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()

        job.retry_count = attempt
        job.last_error = error_msg
        job.updated_at = finished_at

        log_entry.status = JobStatus.FAILED.value
        log_entry.error = tb
        log_entry.finished_at = finished_at

        if attempt >= job.max_retries:
            job.status = JobStatus.FAILED.value
            job.next_retry_at = None
            logger.error(
                "Job id=%s permanently failed after %s attempts: %s",
                job.id,
                attempt,
                error_msg,
            )
        else:
            job.status = JobStatus.PENDING.value
            delay = BACKOFF_BASE ** attempt  # 5, 25, 125
            job.next_retry_at = finished_at + timedelta(seconds=delay)
            logger.warning(
                "Job id=%s failed attempt %s, next retry at %s: %s",
                job.id,
                attempt,
                job.next_retry_at.isoformat(),
                error_msg,
            )

        db.session.commit()

    return job


def run_due_jobs():
    """Find all pending jobs whose next_retry_at has passed and execute them."""
    now = datetime.utcnow()
    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status == JobStatus.PENDING.value,
            db.or_(
                BackgroundJob.next_retry_at.is_(None),
                BackgroundJob.next_retry_at <= now,
            ),
        )
        .order_by(BackgroundJob.created_at)
        .all()
    )
    results = []
    for job in jobs:
        execute_job(job)
        results.append(job)
    return results


def retry_failed_job(job_id: int) -> BackgroundJob | None:
    """Manually retry a permanently failed job by resetting its state."""
    job = db.session.get(BackgroundJob, job_id)
    if job is None:
        return None
    if job.status != JobStatus.FAILED.value:
        return job

    job.status = JobStatus.PENDING.value
    job.next_retry_at = None
    db.session.commit()
    logger.info("Manual retry queued for job id=%s", job.id)
    return execute_job(job)
