import json
import logging
from datetime import datetime, timedelta
from ..extensions import db
from ..models import JobExecution

logger = logging.getLogger("finmind.jobs")

# Backoff schedule in seconds: 30s, 120s, 480s
BACKOFF_MULTIPLIER = 4
BACKOFF_BASE_SECONDS = 30

# Registry of job handlers
_handlers: dict[str, callable] = {}


def register_handler(job_type: str, handler: callable):
    """Register a handler function for a job type."""
    _handlers[job_type] = handler


def enqueue_job(job_type: str, payload: dict | None = None, user_id: int | None = None, max_attempts: int = 3) -> JobExecution:
    """Creates a JobExecution record with status pending."""
    job = JobExecution(
        user_id=user_id,
        job_type=job_type,
        status="pending",
        payload=json.dumps(payload) if payload else None,
        attempts=0,
        max_attempts=max_attempts,
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s type=%s user=%s", job.id, job_type, user_id)
    return job


def execute_job(job_id: int) -> JobExecution:
    """Runs a job with retry logic."""
    job = db.session.get(JobExecution, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    job.status = "running"
    job.attempts += 1
    job.started_at = datetime.utcnow()
    db.session.commit()

    handler = _handlers.get(job.job_type)
    if not handler:
        job.status = "failed"
        job.last_error = f"No handler registered for job type: {job.job_type}"
        db.session.commit()
        logger.error("No handler for job id=%s type=%s", job.id, job.job_type)
        return job

    try:
        payload = json.loads(job.payload) if job.payload else {}
        result = handler(payload)
        if result is False:
            raise RuntimeError("Handler returned False")
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.last_error = None
        db.session.commit()
        logger.info("Job completed id=%s type=%s", job.id, job.job_type)
    except Exception as exc:
        job.last_error = str(exc)
        if job.attempts < job.max_attempts:
            backoff = BACKOFF_BASE_SECONDS * (BACKOFF_MULTIPLIER ** (job.attempts - 1))
            job.status = "retrying"
            job.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff)
            logger.warning(
                "Job retrying id=%s type=%s attempt=%s/%s next_retry=%s error=%s",
                job.id, job.job_type, job.attempts, job.max_attempts,
                job.next_retry_at, exc,
            )
        else:
            job.status = "failed"
            logger.error(
                "Job failed id=%s type=%s attempts=%s error=%s",
                job.id, job.job_type, job.attempts, exc,
            )
        db.session.commit()

    return job


def process_pending_jobs() -> list[JobExecution]:
    """Finds pending/retrying jobs ready to execute and runs them."""
    now = datetime.utcnow()
    jobs = (
        db.session.query(JobExecution)
        .filter(
            JobExecution.status.in_(["pending", "retrying"]),
            db.or_(
                JobExecution.next_retry_at.is_(None),
                JobExecution.next_retry_at <= now,
            ),
        )
        .order_by(JobExecution.created_at)
        .all()
    )
    results = []
    for job in jobs:
        results.append(execute_job(job.id))
    logger.info("Processed %s pending jobs", len(results))
    return results


def get_job_stats(user_id: int | None = None) -> dict:
    """Returns counts by status, recent failures, and success rate."""
    query = db.session.query(JobExecution)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    all_jobs = query.all()
    counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0, "retrying": 0}
    for job in all_jobs:
        if job.status in counts:
            counts[job.status] += 1

    total = len(all_jobs)
    completed = counts["completed"]
    success_rate = round((completed / total) * 100, 1) if total > 0 else 0.0

    recent_failures = (
        query.filter(JobExecution.status == "failed")
        .order_by(JobExecution.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "counts": counts,
        "total": total,
        "success_rate": success_rate,
        "recent_failures": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "last_error": j.last_error,
                "attempts": j.attempts,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in recent_failures
        ],
    }
