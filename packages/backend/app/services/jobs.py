import json
import time
from datetime import datetime, timedelta
from ..extensions import db
from ..models_jobs import BackgroundJob, JobStatus
import logging

logger = logging.getLogger("finmind.jobs")

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 60


def enqueue_job(
    job_type: str,
    payload: dict | None = None,
    user_id: int | None = None,
    scheduled_at: datetime | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
) -> BackgroundJob:
    job = BackgroundJob(
        user_id=user_id,
        job_type=job_type,
        payload=json.dumps(payload) if payload else None,
        status=JobStatus.PENDING.value,
        attempt=0,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        scheduled_at=scheduled_at or datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s type=%s user=%s", job.id, job_type, user_id)
    return job


def process_pending_jobs(limit: int = 50) -> dict:
    now = datetime.utcnow()
    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status.in_([
                JobStatus.PENDING.value,
                JobStatus.RETRYING.value,
            ]),
            BackgroundJob.scheduled_at <= now,
        )
        .order_by(BackgroundJob.scheduled_at.asc())
        .limit(limit)
        .all()
    )

    results = {"processed": 0, "completed": 0, "failed": 0, "dead": 0}

    for job in jobs:
        job.status = JobStatus.RUNNING.value
        job.attempt += 1
        job.started_at = datetime.utcnow()
        db.session.commit()

        try:
            _execute_job(job)
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.utcnow()
            results["completed"] += 1
            logger.info("Job completed id=%s type=%s attempt=%s", job.id, job.job_type, job.attempt)
        except Exception as exc:
            job.last_error = str(exc)[:1000]
            if job.attempt >= job.max_retries:
                job.status = JobStatus.DEAD.value
                job.completed_at = datetime.utcnow()
                results["dead"] += 1
                logger.error(
                    "Job dead id=%s type=%s after %s attempts: %s",
                    job.id, job.job_type, job.attempt, exc,
                )
            else:
                backoff = job.retry_backoff_seconds * (2 ** (job.attempt - 1))
                job.status = JobStatus.RETRYING.value
                job.scheduled_at = datetime.utcnow() + timedelta(seconds=backoff)
                results["failed"] += 1
                logger.warning(
                    "Job retry id=%s type=%s attempt=%s next_at=%s",
                    job.id, job.job_type, job.attempt, job.scheduled_at,
                )

        results["processed"] += 1
        db.session.commit()

    return results


def get_job_stats() -> dict:
    from sqlalchemy import func
    rows = (
        db.session.query(
            BackgroundJob.status,
            func.count(BackgroundJob.id),
        )
        .group_by(BackgroundJob.status)
        .all()
    )
    total = 0
    by_status = {}
    for status, count in rows:
        by_status[status] = count
        total += count
    return {"total": total, "by_status": by_status}


def get_user_jobs(uid: int, limit: int = 50) -> list[dict]:
    jobs = (
        db.session.query(BackgroundJob)
        .filter_by(user_id=uid)
        .order_by(BackgroundJob.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_job_to_dict(j) for j in jobs]


def retry_dead_job(job_id: int, uid: int | None = None) -> BackgroundJob | None:
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return None
    if uid and job.user_id != uid:
        return None
    if job.status != JobStatus.DEAD.value:
        return None
    job.status = JobStatus.PENDING.value
    job.attempt = 0
    job.last_error = None
    job.scheduled_at = datetime.utcnow()
    job.started_at = None
    job.completed_at = None
    db.session.commit()
    logger.info("Retried dead job id=%s", job.id)
    return job


def _execute_job(job: BackgroundJob):
    payload = json.loads(job.payload) if job.payload else {}
    handler = JOB_HANDLERS.get(job.job_type)
    if handler:
        handler(job, payload)
    else:
        raise ValueError(f"unknown job_type: {job.job_type}")


def _handle_send_reminder(job: BackgroundJob, payload: dict):
    from ..models import Reminder
    from ..services.reminders import send_reminder
    reminder_id = payload.get("reminder_id")
    if not reminder_id:
        raise ValueError("reminder_id required")
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder:
        raise ValueError(f"reminder {reminder_id} not found")
    success = send_reminder(reminder)
    if not success:
        raise RuntimeError(f"failed to send reminder {reminder_id}")
    reminder.sent = True


JOB_HANDLERS = {
    "send_reminder": _handle_send_reminder,
}


def _job_to_dict(job: BackgroundJob) -> dict:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "job_type": job.job_type,
        "payload": job.payload,
        "status": job.status,
        "attempt": job.attempt,
        "max_retries": job.max_retries,
        "retry_backoff_seconds": job.retry_backoff_seconds,
        "last_error": job.last_error,
        "scheduled_at": job.scheduled_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    }
