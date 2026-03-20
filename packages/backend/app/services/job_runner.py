"""Resilient background job execution with retry and monitoring.

Features:
- Exponential backoff retry with configurable max retries
- Dead letter queue for permanently failed jobs
- Job status tracking (pending, running, completed, failed, dead_lettered)
- Monitoring metrics: success rate, average duration, failure reasons
- Alerting thresholds for failure rates
"""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from ..extensions import db

logger = logging.getLogger("finmind.jobs")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class BackgroundJob(db.Model):
    """Tracks background job execution with retry metadata."""

    __tablename__ = "background_jobs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    payload = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=JobStatus.PENDING.value, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    max_retries = db.Column(db.Integer, default=3, nullable=False)
    backoff_factor = db.Column(db.Float, default=2.0, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


class JobMetrics(db.Model):
    """Aggregated metrics for job monitoring."""

    __tablename__ = "job_metrics"

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(200), nullable=False)
    period_start = db.Column(db.DateTime, nullable=False)
    total_runs = db.Column(db.Integer, default=0, nullable=False)
    successful = db.Column(db.Integer, default=0, nullable=False)
    failed = db.Column(db.Integer, default=0, nullable=False)
    dead_lettered = db.Column(db.Integer, default=0, nullable=False)
    avg_duration_ms = db.Column(db.Integer, default=0, nullable=False)
    p95_duration_ms = db.Column(db.Integer, default=0, nullable=False)


# In-memory job registry
_job_handlers: dict[str, Callable] = {}


def register_handler(name: str, handler: Callable) -> None:
    _job_handlers[name] = handler


def enqueue(
    name: str,
    payload: str | None = None,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> BackgroundJob:
    job = BackgroundJob(
        name=name,
        payload=payload,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s name=%s", job.id, name)
    return job


def execute(job: BackgroundJob) -> dict[str, Any]:
    handler = _job_handlers.get(job.name)
    if not handler:
        job.status = JobStatus.DEAD_LETTERED.value
        job.last_error = f"No handler registered for '{job.name}'"
        db.session.commit()
        return {"status": "dead_lettered", "error": job.last_error}

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    job.attempts += 1
    db.session.commit()

    start_time = time.monotonic()
    try:
        handler(job.payload)
        elapsed = int((time.monotonic() - start_time) * 1000)
        job.status = JobStatus.COMPLETED.value
        job.duration_ms = elapsed
        job.completed_at = datetime.utcnow()
        job.last_error = None
        db.session.commit()
        logger.info("Job id=%s completed in %dms", job.id, elapsed)
        return {"status": "completed", "duration_ms": elapsed}
    except Exception as exc:
        elapsed = int((time.monotonic() - start_time) * 1000)
        job.duration_ms = elapsed
        job.last_error = traceback.format_exc()
        logger.warning("Job id=%s failed attempt %d: %s", job.id, job.attempts, exc)

        if job.attempts >= job.max_retries:
            job.status = JobStatus.DEAD_LETTERED.value
            db.session.commit()
            return {"status": "dead_lettered", "error": str(exc), "attempts": job.attempts}
        else:
            delay = job.backoff_factor ** job.attempts
            job.status = JobStatus.FAILED.value
            job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
            db.session.commit()
            return {
                "status": "failed",
                "error": str(exc),
                "attempts": job.attempts,
                "next_retry_at": job.next_retry_at.isoformat(),
            }


def process_pending() -> list[dict[str, Any]]:
    now = datetime.utcnow()
    pending = BackgroundJob.query.filter(
        db.or_(
            BackgroundJob.status == JobStatus.PENDING.value,
            db.and_(
                BackgroundJob.status == JobStatus.FAILED.value,
                BackgroundJob.next_retry_at <= now,
            ),
        )
    ).order_by(BackgroundJob.created_at.asc()).limit(10).all()

    results = []
    for job in pending:
        result = execute(job)
        results.append({"job_id": job.id, "name": job.name, **result})
    return results


def get_monitoring_stats(hours: int = 24) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(hours=hours)
    jobs = BackgroundJob.query.filter(BackgroundJob.created_at >= since).all()

    total = len(jobs)
    completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED.value)
    failed = sum(1 for j in jobs if j.status == JobStatus.FAILED.value)
    dead = sum(1 for j in jobs if j.status == JobStatus.DEAD_LETTERED.value)
    durations = [j.duration_ms for j in jobs if j.duration_ms]

    success_rate = (completed / total * 100) if total else 0
    avg_duration = int(sum(durations) / len(durations)) if durations else 0
    p95_duration = sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else avg_duration

    # Failure breakdown
    failure_reasons: dict[str, int] = {}
    for j in jobs:
        if j.last_error and j.status in (JobStatus.FAILED.value, JobStatus.DEAD_LETTERED.value):
            reason = j.last_error.split("\n")[-2].strip() if "\n" in j.last_error else j.last_error[:100]
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    return {
        "period_hours": hours,
        "total_jobs": total,
        "completed": completed,
        "failed": failed,
        "dead_lettered": dead,
        "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING.value),
        "running": sum(1 for j in jobs if j.status == JobStatus.RUNNING.value),
        "success_rate_pct": round(success_rate, 1),
        "avg_duration_ms": avg_duration,
        "p95_duration_ms": p95_duration,
        "failure_reasons": dict(sorted(failure_reasons.items(), key=lambda x: -x[1])[:10]),
        "alert": success_rate < 90 and total >= 5,
    }
