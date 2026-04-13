import json
import logging
from datetime import datetime, timedelta

from ..extensions import db
from ..models import BackgroundJob, JobStatus
from .reminders import send_reminder

logger = logging.getLogger("finmind.job_runner")

# Registry of job type -> callable(payload_dict) -> result string
_JOB_REGISTRY: dict[str, callable] = {}


def _register(job_type: str):
    def decorator(fn):
        _JOB_REGISTRY[job_type] = fn
        return fn
    return decorator


def compute_backoff_delay(attempts: int) -> int:
    """Exponential backoff: delay = min(300, 30 * 2^attempts) seconds."""
    return min(300, 30 * (2 ** attempts))


def create_job(
    job_type: str,
    payload: dict,
    user_id: int | None = None,
    max_attempts: int = 3,
) -> BackgroundJob:
    """Create a new background job in PENDING status."""
    job = BackgroundJob(
        user_id=user_id,
        job_type=job_type,
        payload=json.dumps(payload),
        status=JobStatus.PENDING,
        max_attempts=max_attempts,
    )
    db.session.add(job)
    db.session.flush()
    return job


def execute_job(job: BackgroundJob) -> None:
    """Execute a single job based on job_type, updating status."""
    handler = _JOB_REGISTRY.get(job.job_type)
    if handler is None:
        job.status = JobStatus.FAILED
        job.last_error = f"Unknown job type: {job.job_type}"
        job.completed_at = datetime.utcnow()
        db.session.commit()
        logger.error("Job %s has unknown type %s", job.id, job.job_type)
        return

    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        payload = json.loads(job.payload)
        result = handler(payload)
        job.status = JobStatus.SUCCEEDED
        job.result = json.dumps(result) if result else None
        job.completed_at = datetime.utcnow()
        db.session.commit()
        logger.info("Job %s succeeded on attempt %s", job.id, job.attempts)
    except Exception as exc:
        job.last_error = str(exc)
        logger.warning(
            "Job %s failed on attempt %s: %s", job.id, job.attempts, exc
        )
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            logger.error(
                "Job %s exhausted %s attempts, marked FAILED", job.id, job.max_attempts
            )
        else:
            job.status = JobStatus.RETRYING
            delay = compute_backoff_delay(job.attempts)
            job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
            logger.info(
                "Job %s will retry in %s seconds (attempt %s/%s)",
                job.id,
                delay,
                job.attempts,
                job.max_attempts,
            )
        db.session.commit()


def retry_failed_jobs() -> int:
    """Find RETRYING jobs whose next_retry_at <= now, re-execute them. Returns count."""
    now = datetime.utcnow()
    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status == JobStatus.RETRYING,
            BackgroundJob.next_retry_at <= now,
        )
        .all()
    )
    for job in jobs:
        execute_job(job)
    return len(jobs)


def retry_specific_job(job: BackgroundJob) -> None:
    """Manually retry a specific job (resets retry timing)."""
    job.status = JobStatus.PENDING
    job.next_retry_at = None
    db.session.commit()
    execute_job(job)


# --- Job handlers ---

@_register("send_reminder")
def _handle_send_reminder(payload: dict) -> dict:
    """Send a reminder via the reminder service.

    Payload: {"reminder_id": int}
    """
    from ..models import Reminder

    reminder_id = payload.get("reminder_id")
    if reminder_id is None:
        raise ValueError("reminder_id is required in payload")

    reminder = db.session.get(Reminder, reminder_id)
    if reminder is None:
        raise ValueError(f"Reminder {reminder_id} not found")

    ok = send_reminder(reminder)
    if not ok:
        raise RuntimeError(f"send_reminder returned False for reminder {reminder_id}")

    reminder.sent = True
    db.session.commit()
    return {"reminder_id": reminder_id, "sent": True}
