"""Resilient background job retry & monitoring.

Track job execution, automatic retries with exponential backoff,
dead letter queue, and monitoring dashboard.
"""

import json
import math
from datetime import datetime, timedelta
from ..extensions import db


class BackgroundJob(db.Model):
    __tablename__ = "background_jobs"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    job_type = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.Text, default="{}")
    status = db.Column(db.String(20), default="pending")  # pending, running, completed, failed, dead
    priority = db.Column(db.Integer, default=0)
    attempts = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    last_error = db.Column(db.Text, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class JobLog(db.Model):
    __tablename__ = "job_logs"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("background_jobs.id"), nullable=False)
    attempt = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


JOB_TYPES = ["email", "notification", "report", "sync", "cleanup", "export", "import"]


def create_job(name: str, job_type: str, payload: dict | None = None,
               max_retries: int = 3, priority: int = 0) -> dict:
    if job_type not in JOB_TYPES:
        raise ValueError(f"Unknown job type: {job_type}")

    job = BackgroundJob(
        name=name, job_type=job_type, payload=json.dumps(payload or {}),
        max_retries=max_retries, priority=priority,
    )
    db.session.add(job)
    db.session.commit()
    return _serialize_job(job)


def start_job(job_id: int) -> dict:
    job = BackgroundJob.query.get(job_id)
    if not job:
        raise ValueError("Job not found")
    if job.status not in ("pending", "failed"):
        raise ValueError(f"Cannot start job in {job.status} status")

    job.status = "running"
    job.started_at = datetime.utcnow()
    job.attempts += 1
    db.session.commit()

    _log(job.id, job.attempts, "running", "Job started")
    return _serialize_job(job)


def complete_job(job_id: int, message: str = "", duration_ms: int = 0) -> dict:
    job = BackgroundJob.query.get(job_id)
    if not job:
        raise ValueError("Job not found")

    job.status = "completed"
    job.completed_at = datetime.utcnow()
    db.session.commit()

    _log(job.id, job.attempts, "completed", message, duration_ms)
    return _serialize_job(job)


def fail_job(job_id: int, error: str, duration_ms: int = 0) -> dict:
    job = BackgroundJob.query.get(job_id)
    if not job:
        raise ValueError("Job not found")

    job.last_error = error
    _log(job.id, job.attempts, "failed", error, duration_ms)

    if job.attempts < job.max_retries:
        # Exponential backoff: 2^attempt * 30 seconds
        delay = timedelta(seconds=30 * math.pow(2, job.attempts))
        job.status = "failed"
        job.next_retry_at = datetime.utcnow() + delay
    else:
        job.status = "dead"
        job.next_retry_at = None

    db.session.commit()
    return _serialize_job(job)


def retry_due_jobs() -> list[dict]:
    """Find and restart jobs that are due for retry."""
    now = datetime.utcnow()
    jobs = BackgroundJob.query.filter(
        BackgroundJob.status == "failed",
        BackgroundJob.next_retry_at <= now,
        BackgroundJob.attempts < BackgroundJob.max_retries,
    ).all()

    results = []
    for job in jobs:
        job.status = "pending"
        results.append(_serialize_job(job))
    db.session.commit()
    return results


def get_job(job_id: int) -> dict | None:
    job = BackgroundJob.query.get(job_id)
    return _serialize_job(job) if job else None


def list_jobs(status: str | None = None, job_type: str | None = None,
              limit: int = 50) -> list[dict]:
    q = BackgroundJob.query
    if status:
        q = q.filter_by(status=status)
    if job_type:
        q = q.filter_by(job_type=job_type)
    jobs = q.order_by(BackgroundJob.created_at.desc()).limit(limit).all()
    return [_serialize_job(j) for j in jobs]


def get_dead_letter_queue(limit: int = 50) -> list[dict]:
    jobs = (BackgroundJob.query.filter_by(status="dead")
            .order_by(BackgroundJob.created_at.desc()).limit(limit).all())
    return [_serialize_job(j) for j in jobs]


def requeue_dead(job_id: int) -> dict:
    job = BackgroundJob.query.get(job_id)
    if not job or job.status != "dead":
        raise ValueError("Job not found in dead letter queue")
    job.status = "pending"
    job.attempts = 0
    job.last_error = None
    job.next_retry_at = None
    db.session.commit()
    _log(job.id, 0, "requeued", "Manually requeued from DLQ")
    return _serialize_job(job)


def get_logs(job_id: int) -> list[dict]:
    logs = (JobLog.query.filter_by(job_id=job_id)
            .order_by(JobLog.created_at).all())
    return [{"attempt": l.attempt, "status": l.status, "message": l.message,
             "duration_ms": l.duration_ms, "created_at": l.created_at.isoformat()}
            for l in logs]


def get_stats() -> dict:
    from sqlalchemy import func
    counts = dict(db.session.query(BackgroundJob.status, func.count(BackgroundJob.id))
                  .group_by(BackgroundJob.status).all())
    return {
        "pending": counts.get("pending", 0),
        "running": counts.get("running", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "dead": counts.get("dead", 0),
        "total": sum(counts.values()),
    }


def _log(job_id: int, attempt: int, status: str, message: str = "",
         duration_ms: int = 0):
    log = JobLog(job_id=job_id, attempt=attempt, status=status,
                 message=message, duration_ms=duration_ms)
    db.session.add(log)
    db.session.commit()


def _serialize_job(job: BackgroundJob) -> dict:
    return {
        "id": job.id, "name": job.name, "job_type": job.job_type,
        "payload": json.loads(job.payload), "status": job.status,
        "priority": job.priority, "attempts": job.attempts,
        "max_retries": job.max_retries, "last_error": job.last_error,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "created_at": job.created_at.isoformat(),
    }
