"""Resilient background job manager with exponential backoff retry and dead-letter queue."""

from __future__ import annotations

import logging
import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from ..extensions import db
from ..models import Job as JobModel

logger = logging.getLogger("finmind.job_manager")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY_SECONDS = 2.0
DEFAULT_MAX_DELAY_SECONDS = 300.0
DEFAULT_JITTER = True


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEAD = "DEAD"  # moved to dead-letter queue after max retries


# ---------------------------------------------------------------------------
# Pure helpers (no side-effects)
# ---------------------------------------------------------------------------


def compute_backoff_delay(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    jitter: bool = DEFAULT_JITTER,
) -> float:
    """Return exponential backoff delay in seconds for a given *attempt* (0-based).

    Formula: min(base * 2^attempt, max_delay), optionally with simple jitter.
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        # deterministic "jitter" based on attempt to keep the function pure
        delay = delay * (0.5 + 0.5 * ((attempt * 7 + 3) % 10) / 10.0)
    return round(delay, 3)


# ---------------------------------------------------------------------------
# In-memory job registry (maps job-type names to callables)
# ---------------------------------------------------------------------------

_JOB_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_job_type(name: str, func: Callable[..., Any]) -> None:
    """Register a callable under *name* so the manager can invoke it later."""
    _JOB_REGISTRY[name] = func


def get_registered_types() -> list[str]:
    return sorted(_JOB_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Service functions (work with the DB-backed Job model)
# ---------------------------------------------------------------------------


def enqueue(
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    scheduled_at: datetime | None = None,
) -> JobModel:
    """Create a new job record in PENDING state and return it."""
    now = datetime.utcnow()
    job = JobModel(
        job_type=job_type,
        payload=payload or {},
        status=JobStatus.PENDING.value,
        max_retries=max_retries,
        attempt=0,
        scheduled_at=scheduled_at or now,
        created_at=now,
        updated_at=now,
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s type=%s", job.id, job_type)
    return job


def run_job(job_id: int) -> JobModel:
    """Execute a single job by *job_id*, handling retries and dead-lettering.

    Returns the refreshed job record.
    """
    job: JobModel | None = db.session.get(JobModel, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    if job.status not in (JobStatus.PENDING.value, JobStatus.FAILED.value):
        logger.warning("Job %s has status %s, skipping", job_id, job.status)
        return job

    func = _JOB_REGISTRY.get(job.job_type)
    if func is None:
        job.status = JobStatus.DEAD.value
        job.error_message = f"Unknown job type: {job.job_type}"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        logger.error("Dead-lettered job %s: unknown type %s", job_id, job.job_type)
        return job

    job.status = JobStatus.RUNNING.value
    job.attempt = (job.attempt or 0) + 1
    job.updated_at = datetime.utcnow()
    db.session.commit()

    try:
        func(job.payload)
        job.status = JobStatus.SUCCESS.value
        job.error_message = None
        job.completed_at = datetime.utcnow()
        job.updated_at = job.completed_at
        db.session.commit()
        logger.info("Job %s succeeded on attempt %s", job_id, job.attempt)
    except Exception as exc:
        _handle_failure(job, exc)

    return job


def retry_failed_job(job_id: int) -> JobModel:
    """Reset a FAILED or DEAD job back to PENDING so it can be retried."""
    job: JobModel | None = db.session.get(JobModel, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    if job.status not in (JobStatus.FAILED.value, JobStatus.DEAD.value):
        raise ValueError(f"Job {job_id} is {job.status}, cannot retry")

    job.status = JobStatus.PENDING.value
    job.attempt = 0
    job.error_message = None
    job.next_retry_at = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Reset job %s to PENDING for manual retry", job_id)
    return job


def process_pending_jobs(*, limit: int = 50) -> list[JobModel]:
    """Find and run pending jobs that are due.  Returns list of processed jobs."""
    now = datetime.utcnow()
    jobs = (
        db.session.query(JobModel)
        .filter(
            JobModel.status.in_([JobStatus.PENDING.value, JobStatus.FAILED.value]),
            JobModel.scheduled_at <= now,
            db.or_(JobModel.next_retry_at.is_(None), JobModel.next_retry_at <= now),
        )
        .order_by(JobModel.scheduled_at)
        .limit(limit)
        .all()
    )
    results: list[JobModel] = []
    for job in jobs:
        results.append(run_job(job.id))
    return results


def list_jobs(
    *,
    status: str | None = None,
    job_type: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[JobModel], int]:
    """Return a paginated list of jobs, optionally filtered."""
    query = db.session.query(JobModel)
    if status:
        query = query.filter(JobModel.status == status)
    if job_type:
        query = query.filter(JobModel.job_type == job_type)
    total = query.count()
    items = (
        query.order_by(JobModel.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return items, total


def get_job(job_id: int) -> JobModel | None:
    return db.session.get(JobModel, job_id)


def dead_letter_jobs(*, page: int = 1, per_page: int = 20) -> tuple[list[JobModel], int]:
    """Return jobs in the dead-letter queue."""
    return list_jobs(status=JobStatus.DEAD.value, page=page, per_page=per_page)


def job_stats() -> dict[str, int]:
    """Return counts per status."""
    rows = (
        db.session.query(JobModel.status, db.func.count(JobModel.id))
        .group_by(JobModel.status)
        .all()
    )
    return {status: count for status, count in rows}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _handle_failure(job: JobModel, exc: Exception) -> None:
    """Transition job to FAILED or DEAD depending on retry budget."""
    job.error_message = str(exc)[:500]
    job.updated_at = datetime.utcnow()

    if job.attempt >= job.max_retries:
        job.status = JobStatus.DEAD.value
        db.session.commit()
        logger.error(
            "Job %s dead-lettered after %s attempts: %s",
            job.id,
            job.attempt,
            exc,
        )
    else:
        delay = compute_backoff_delay(job.attempt - 1)
        job.status = JobStatus.FAILED.value
        job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        db.session.commit()
        logger.warning(
            "Job %s failed on attempt %s, next retry in %.1fs: %s",
            job.id,
            job.attempt,
            delay,
            exc,
        )
