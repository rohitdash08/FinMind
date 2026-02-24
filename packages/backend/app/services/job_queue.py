"""Resilient background job queue with retry logic and monitoring (#130).

Provides a simple in-process job queue backed by SQLAlchemy for persistence.
Jobs support configurable max retries with exponential backoff.
"""

import logging
import traceback
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, Optional

from ..extensions import db

logger = logging.getLogger("finmind.job_queue")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class BackgroundJob(db.Model):
    __tablename__ = "background_jobs"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), default=JobStatus.PENDING.value, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    max_retries = db.Column(db.Integer, default=3, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# Registry of job handlers
_handlers: Dict[str, Callable] = {}


def register_handler(name: str, handler: Callable) -> None:
    """Register a named job handler function."""
    _handlers[name] = handler


def enqueue(name: str, payload: dict = None, max_retries: int = 3) -> BackgroundJob:
    """Create a new background job."""
    if name not in _handlers:
        raise ValueError(f"No handler registered for job '{name}'")
    job = BackgroundJob(name=name, payload=payload or {}, max_retries=max_retries)
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s name=%s", job.id, name)
    return job


def process_pending() -> int:
    """Process all pending/retrying jobs. Returns count of jobs processed."""
    now = datetime.utcnow()
    jobs = (
        BackgroundJob.query
        .filter(
            BackgroundJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRYING.value]),
            db.or_(
                BackgroundJob.next_retry_at.is_(None),
                BackgroundJob.next_retry_at <= now,
            ),
        )
        .order_by(BackgroundJob.created_at)
        .all()
    )

    processed = 0
    for job in jobs:
        _execute_job(job)
        processed += 1

    return processed


def _execute_job(job: BackgroundJob) -> None:
    """Execute a single job with error handling and retry logic."""
    handler = _handlers.get(job.name)
    if not handler:
        job.status = JobStatus.FAILED.value
        job.last_error = f"No handler for '{job.name}'"
        db.session.commit()
        return

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    job.attempts += 1
    db.session.commit()

    try:
        handler(job.payload)
        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        job.last_error = None
        logger.info("Job id=%s completed (attempt %s)", job.id, job.attempts)
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        job.last_error = error_msg[:2000]

        if job.attempts < job.max_retries:
            backoff = min(2 ** job.attempts * 30, 3600)  # 30s, 60s, 120s... max 1h
            job.status = JobStatus.RETRYING.value
            job.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff)
            logger.warning(
                "Job id=%s failed (attempt %s/%s), retry in %ss: %s",
                job.id, job.attempts, job.max_retries, backoff, exc,
            )
        else:
            job.status = JobStatus.FAILED.value
            logger.error(
                "Job id=%s permanently failed after %s attempts: %s",
                job.id, job.attempts, exc,
            )

    db.session.commit()


def get_job_stats() -> dict:
    """Return job queue statistics."""
    from sqlalchemy import func
    rows = (
        db.session.query(BackgroundJob.status, func.count(BackgroundJob.id))
        .group_by(BackgroundJob.status)
        .all()
    )
    stats = {s.value: 0 for s in JobStatus}
    for status, count in rows:
        stats[status] = count
    stats["total"] = sum(stats.values())
    return stats
