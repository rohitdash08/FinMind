import json
import logging
import time
import traceback
from datetime import datetime, timedelta

from ..extensions import db
from ..models import BackgroundJob, JobStatus, JobType, Reminder
from ..services.reminders import send_reminder

logger = logging.getLogger("finmind.jobs")

# Exponential backoff intervals in seconds: 30s, 2min, 8min
BACKOFF_INTERVALS = [30, 120, 480]


def enqueue_job(
    user_id: int,
    job_type: str,
    payload: dict | None = None,
    max_attempts: int = 3,
) -> BackgroundJob:
    """Create a new PENDING background job."""
    job = BackgroundJob(
        user_id=user_id,
        job_type=job_type,
        payload=json.dumps(payload or {}),
        status=JobStatus.PENDING.value,
        attempts=0,
        max_attempts=max_attempts,
        next_retry_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    logger.info(
        "Enqueued job id=%s type=%s user=%s", job.id, job_type, user_id
    )
    return job


def process_pending_jobs() -> dict:
    """Find and process all due jobs. Returns processing summary."""
    now = datetime.utcnow()
    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status.in_(
                [JobStatus.PENDING.value, JobStatus.FAILED.value]
            ),
            db.or_(
                BackgroundJob.next_retry_at.is_(None),
                BackgroundJob.next_retry_at <= now,
            ),
        )
        .order_by(BackgroundJob.created_at)
        .all()
    )

    results = {"processed": 0, "succeeded": 0, "failed": 0, "dead": 0}
    for job in jobs:
        result = execute_job(job)
        results["processed"] += 1
        if result == "completed":
            results["succeeded"] += 1
        elif result == "dead":
            results["dead"] += 1
        else:
            results["failed"] += 1

    logger.info("Job processing complete: %s", results)
    return results


def execute_job(job: BackgroundJob) -> str:
    """Execute a single job, handling retries and dead-lettering."""
    from flask import current_app

    job.status = JobStatus.RUNNING.value
    job.attempts += 1
    job.updated_at = datetime.utcnow()
    db.session.commit()

    start = time.perf_counter()
    obs = current_app.extensions.get("observability")

    try:
        _dispatch_job(job)
        elapsed = time.perf_counter() - start

        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        job.last_error = None
        job.updated_at = datetime.utcnow()
        db.session.commit()

        if obs:
            obs.record_job_completed(job.job_type, elapsed)
        logger.info(
            "Job completed id=%s type=%s elapsed=%.3fs",
            job.id,
            job.job_type,
            elapsed,
        )
        return "completed"

    except Exception as exc:
        elapsed = time.perf_counter() - start
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        job.last_error = error_msg[:2000]
        job.updated_at = datetime.utcnow()

        if job.attempts >= job.max_attempts:
            # Dead letter: exceeded max attempts
            job.status = JobStatus.DEAD.value
            db.session.commit()
            if obs:
                obs.record_job_dead_letter(job.job_type)
            logger.error(
                "Job dead-lettered id=%s type=%s attempts=%s error=%s",
                job.id,
                job.job_type,
                job.attempts,
                str(exc),
            )
            return "dead"
        else:
            # Schedule retry with exponential backoff
            backoff_idx = min(job.attempts - 1, len(BACKOFF_INTERVALS) - 1)
            backoff_seconds = BACKOFF_INTERVALS[backoff_idx]
            job.status = JobStatus.FAILED.value
            job.next_retry_at = datetime.utcnow() + timedelta(
                seconds=backoff_seconds
            )
            db.session.commit()
            if obs:
                obs.record_job_retry(job.job_type)
            logger.warning(
                "Job failed id=%s type=%s attempt=%s/%s "
                "next_retry_at=%s error=%s",
                job.id,
                job.job_type,
                job.attempts,
                job.max_attempts,
                job.next_retry_at.isoformat(),
                str(exc),
            )
            return "failed"


def _dispatch_job(job: BackgroundJob) -> None:
    """Route job to appropriate handler based on job_type."""
    payload = json.loads(job.payload)

    if job.job_type == JobType.REMINDER.value:
        _handle_reminder_job(job.user_id, payload)
    elif job.job_type == JobType.DIGEST.value:
        _handle_digest_job(job.user_id, payload)
    else:
        raise ValueError(f"Unknown job type: {job.job_type}")


def _handle_reminder_job(user_id: int, payload: dict) -> None:
    """Process a single reminder job."""
    reminder_id = payload.get("reminder_id")
    if not reminder_id:
        raise ValueError("Missing reminder_id in job payload")

    reminder = db.session.get(Reminder, reminder_id)
    if not reminder:
        raise ValueError(f"Reminder {reminder_id} not found")
    if reminder.user_id != user_id:
        raise ValueError(f"Reminder {reminder_id} does not belong to user")
    if reminder.sent:
        logger.info("Reminder %s already sent, skipping", reminder_id)
        return

    success = send_reminder(reminder)
    if not success:
        raise RuntimeError(f"Failed to send reminder {reminder_id}")

    reminder.sent = True
    db.session.commit()


def _handle_digest_job(user_id: int, payload: dict) -> None:
    """Process a digest generation job (placeholder for future use)."""
    logger.info("Digest job processed for user=%s payload=%s", user_id, payload)


def get_job_status(job_id: int) -> dict | None:
    """Return job details as a dictionary."""
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return None
    return _serialize_job(job)


def get_job_stats() -> dict:
    """Return aggregate job statistics."""
    stats = {}
    for status in JobStatus:
        count = (
            db.session.query(BackgroundJob)
            .filter_by(status=status.value)
            .count()
        )
        stats[status.value.lower()] = count
    stats["total"] = sum(stats.values())
    return stats


def cleanup_old_jobs(days: int = 30) -> int:
    """Remove completed jobs older than the specified number of days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status == JobStatus.COMPLETED.value,
            BackgroundJob.completed_at <= cutoff,
        )
        .delete(synchronize_session=False)
    )
    db.session.commit()
    logger.info("Cleaned up %s old completed jobs", deleted)
    return deleted


def _serialize_job(job: BackgroundJob) -> dict:
    """Serialize a BackgroundJob to a dictionary."""
    return {
        "id": job.id,
        "user_id": job.user_id,
        "job_type": job.job_type,
        "payload": json.loads(job.payload),
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "next_retry_at": (
            job.next_retry_at.isoformat() if job.next_retry_at else None
        ),
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": (
            job.completed_at.isoformat() if job.completed_at else None
        ),
    }
