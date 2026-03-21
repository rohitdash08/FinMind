import functools
import logging
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Callable

from ..extensions import db
from ..models import BackgroundJob, JobHistory, JobStatus

logger = logging.getLogger("finmind.job_retry")

_lock = threading.Lock()


def create_job(name: str, max_retries: int = 3) -> BackgroundJob:
    job = BackgroundJob(name=name, max_retries=max_retries)
    db.session.add(job)
    db.session.commit()
    logger.info("Created job id=%s name=%s max_retries=%s", job.id, name, max_retries)
    return job


def execute_job(
    job: BackgroundJob,
    func: Callable,
    *args,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs,
) -> BackgroundJob:
    with _lock:
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.utcnow()
        db.session.commit()

    while job.attempts < job.max_retries:
        job.attempts += 1
        try:
            result = func(*args, **kwargs)
            with _lock:
                job.status = JobStatus.SUCCESS.value
                job.result = str(result) if result is not None else None
                job.completed_at = datetime.utcnow()
                job.last_error = None
                _record_history(job, JobStatus.SUCCESS.value)
                db.session.commit()
            logger.info("Job id=%s succeeded on attempt %s", job.id, job.attempts)
            return job
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            delay = base_delay * (backoff_factor ** (job.attempts - 1))
            with _lock:
                job.last_error = error_msg
                if job.attempts < job.max_retries:
                    job.status = JobStatus.RETRYING.value
                    job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                    _record_history(job, JobStatus.RETRYING.value, error_msg)
                else:
                    job.status = JobStatus.DEAD.value
                    job.completed_at = datetime.utcnow()
                    _record_history(job, JobStatus.DEAD.value, error_msg)
                db.session.commit()
            logger.warning(
                "Job id=%s attempt %s/%s failed: %s",
                job.id, job.attempts, job.max_retries, error_msg,
            )
            if job.attempts < job.max_retries:
                time.sleep(delay)

    return job


def retry_failed_jobs(max_jobs: int = 10) -> list[int]:
    now = datetime.utcnow()
    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status.in_([JobStatus.FAILED.value, JobStatus.RETRYING.value]),
            BackgroundJob.attempts < BackgroundJob.max_retries,
        )
        .filter(
            db.or_(
                BackgroundJob.next_retry_at.is_(None),
                BackgroundJob.next_retry_at <= now,
            )
        )
        .limit(max_jobs)
        .all()
    )
    return [j.id for j in jobs]


def get_job_stats() -> dict:
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


def get_dead_letter_jobs(limit: int = 50) -> list[dict]:
    jobs = (
        db.session.query(BackgroundJob)
        .filter_by(status=JobStatus.DEAD.value)
        .order_by(BackgroundJob.completed_at.desc())
        .limit(limit)
        .all()
    )
    return [_job_to_dict(j) for j in jobs]


def get_job_history(job_id: int) -> list[dict]:
    entries = (
        db.session.query(JobHistory)
        .filter_by(job_id=job_id)
        .order_by(JobHistory.attempt)
        .all()
    )
    return [
        {
            "attempt": h.attempt,
            "status": h.status,
            "error": h.error,
            "created_at": h.created_at.isoformat(),
        }
        for h in entries
    ]


def resilient_job(name: str = "", max_retries: int = 3, base_delay: float = 1.0):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            job_name = name or func.__name__
            job = create_job(job_name, max_retries=max_retries)
            return execute_job(job, func, *args, base_delay=base_delay, **kwargs)
        return wrapper
    return decorator


def _record_history(job: BackgroundJob, status: str, error: str | None = None):
    entry = JobHistory(
        job_id=job.id,
        attempt=job.attempts,
        status=status,
        error=error,
    )
    db.session.add(entry)


def _job_to_dict(j: BackgroundJob) -> dict:
    return {
        "id": j.id,
        "name": j.name,
        "status": j.status,
        "attempts": j.attempts,
        "max_retries": j.max_retries,
        "last_error": j.last_error,
        "result": j.result,
        "created_at": j.created_at.isoformat(),
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "next_retry_at": j.next_retry_at.isoformat() if j.next_retry_at else None,
    }
