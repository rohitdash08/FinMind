"""Background job worker.

Runs via APScheduler, dequeuing jobs from Redis and executing them
with exponential-backoff retry logic.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from ..extensions import db, redis_client
from .job_queue import (
    QUEUE_KEY,
    PROCESSING_KEY,
    DEAD_LETTER_KEY,
    JobStatus,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_JOB_TIMEOUT,
    _job_key,
    _lock_key,
    save_job_metadata,
    load_job_metadata,
    _update_job_status,
)

logger = logging.getLogger("finmind.jobs.worker")

# ---------------------------------------------------------------------------
# Registry of job handlers
# ---------------------------------------------------------------------------
_HANDLERS: Dict[str, Callable[..., Any]] = {}


def register_handler(job_type: str):
    """Decorator to register a job handler function."""

    def decorator(fn: Callable) -> Callable:
        _HANDLERS[job_type] = fn
        return fn

    return decorator


def get_handler(job_type: str) -> Optional[Callable]:
    return _HANDLERS.get(job_type)


# ---------------------------------------------------------------------------
# Built-in handlers (example stubs – expand as needed)
# ---------------------------------------------------------------------------

@register_handler("send_reminder")
def _handle_send_reminder(payload: dict) -> dict:
    """Send a reminder notification."""
    from .reminders import send_reminder
    from ..models import Reminder

    reminder_id = payload.get("reminder_id")
    if reminder_id is None:
        raise ValueError("reminder_id required")

    reminder = db.session.get(Reminder, reminder_id)
    if reminder is None:
        raise ValueError(f"Reminder {reminder_id} not found")

    ok = send_reminder(reminder)
    return {"sent": ok}


@register_handler("import_expenses")
def _handle_import_expenses(payload: dict) -> dict:
    """Import expenses from a file."""
    from .expense_import import import_csv

    file_path = payload["file_path"]
    user_id = payload["user_id"]
    result = import_csv(file_path, user_id)
    return result


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _compute_backoff(attempt: int, base: float = DEFAULT_RETRY_DELAY) -> float:
    """Exponential backoff: base * 2^attempt, capped at 1 hour."""
    delay = base * (2 ** attempt)
    return min(delay, 3600)


def _acquire_lock(job_id: str, timeout: int = DEFAULT_JOB_TIMEOUT) -> bool:
    """Try to acquire a distributed lock for a job."""
    return redis_client.set(
        _lock_key(job_id),
        "1",
        nx=True,
        ex=timeout,
    )


def _release_lock(job_id: str) -> None:
    redis_client.delete(_lock_key(job_id))


def process_next_job(app=None) -> bool:
    """Dequeue and execute the highest-priority pending job.

    Returns True if a job was processed, False if the queue was empty.
    """
    # Pop the lowest-score (highest-priority) job
    results = redis_client.zpopmin(QUEUE_KEY, count=1)
    if not results:
        return False

    job_id, _score = results[0]

    if not _acquire_lock(job_id):
        # Another worker grabbed it; push it back
        redis_client.zadd(QUEUE_KEY, {job_id: _score})
        return False

    meta = load_job_metadata(job_id)
    if meta is None:
        logger.warning("Job %s metadata missing, discarding", job_id)
        _release_lock(job_id)
        return True

    job_type = meta["job_type"]
    payload = meta.get("payload", {})
    attempts = meta.get("attempts", 0)
    max_retries = meta.get("max_retries", DEFAULT_MAX_RETRIES)

    handler = get_handler(job_type)
    if handler is None:
        logger.error("No handler registered for job type %s", job_type)
        _fail_job(job_id, meta, f"No handler for job type: {job_type}", is_dead=True)
        _release_lock(job_id)
        return True

    # Mark running
    meta["status"] = JobStatus.RUNNING
    meta["attempts"] = attempts + 1
    meta["started_at"] = datetime.utcnow().isoformat()
    save_job_metadata(job_id, meta)
    _update_job_status(job_id, JobStatus.RUNNING, increment_attempts=True)

    redis_client.lpush(PROCESSING_KEY, job_id)

    logger.info("Processing job %s [%s] attempt %d/%d", job_id, job_type, attempts + 1, max_retries)

    try:
        result = handler(payload)
        # Success
        meta["status"] = JobStatus.COMPLETED
        meta["completed_at"] = datetime.utcnow().isoformat()
        meta["result"] = result
        save_job_metadata(job_id, meta)
        _update_job_status(job_id, JobStatus.COMPLETED, result=result)
        redis_client.lrem(PROCESSING_KEY, 0, job_id)
        logger.info("Job %s completed successfully", job_id)
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Job %s failed: %s", job_id, error_msg, exc_info=True)

        if attempts + 1 >= max_retries:
            # Move to dead-letter queue
            _fail_job(job_id, meta, error_msg, is_dead=True)
        else:
            # Schedule retry with backoff
            backoff = _compute_backoff(attempts)
            retry_at = datetime.utcnow() + timedelta(seconds=backoff)
            meta["status"] = JobStatus.RETRYING
            meta["last_error"] = error_msg
            meta["next_retry_at"] = retry_at.isoformat()
            save_job_metadata(job_id, meta)
            _update_job_status(
                job_id,
                JobStatus.RETRYING,
                error=error_msg,
                next_retry_at=retry_at,
            )
            redis_client.lrem(PROCESSING_KEY, 0, job_id)
            # Schedule re-enqueue via sorted-set with future timestamp as score
            redis_client.zadd(QUEUE_KEY, {job_id: retry_at.timestamp()})
            logger.info(
                "Job %s scheduled for retry in %.0fs (attempt %d/%d)",
                job_id, backoff, attempts + 1, max_retries,
            )

    _release_lock(job_id)
    return True


def _fail_job(job_id: str, meta: dict, error: str, is_dead: bool = False) -> None:
    """Mark a job as failed or dead."""
    status = JobStatus.DEAD if is_dead else JobStatus.FAILED
    meta["status"] = status
    meta["last_error"] = error
    meta["completed_at"] = datetime.utcnow().isoformat()
    save_job_metadata(job_id, meta)
    _update_job_status(job_id, status, error=error)
    redis_client.lrem(PROCESSING_KEY, 0, job_id)
    if is_dead:
        redis_client.lpush(DEAD_LETTER_KEY, job_id)
    logger.warning("Job %s marked as %s: %s", job_id, status, error)


def process_batch(batch_size: int = 10, app=None) -> int:
    """Process up to `batch_size` jobs from the queue."""
    processed = 0
    for _ in range(batch_size):
        if not process_next_job(app):
            break
        processed += 1
    return processed


def retry_scheduled_jobs() -> int:
    """Re-enqueue jobs whose retry time has arrived.

    Returns the number of jobs re-enqueued.
    """
    now = time.time()
    # Find jobs in queue with score <= now (scheduled retries)
    jobs = redis_client.zrangebyscore(QUEUE_KEY, "-inf", now, start=0, num=50)
    requeued = 0
    for job_id in jobs:
        meta = load_job_metadata(job_id)
        if meta and meta.get("status") == JobStatus.RETRYING:
            # Reset priority score
            redis_client.zadd(QUEUE_KEY, {job_id: meta.get("priority", 5)})
            requeued += 1
    return requeued


# ---------------------------------------------------------------------------
# Prometheus metrics integration
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Gauge, Histogram

    JOBS_ENQUEUED = Counter(
        "finmind_jobs_enqueued_total",
        "Total jobs enqueued",
        ["job_type", "queue"],
    )
    JOBS_COMPLETED = Counter(
        "finmind_jobs_completed_total",
        "Total jobs completed successfully",
        ["job_type", "queue"],
    )
    JOBS_FAILED = Counter(
        "finmind_jobs_failed_total",
        "Total jobs failed (including retries)",
        ["job_type", "queue"],
    )
    JOBS_DEAD = Counter(
        "finmind_jobs_dead_total",
        "Total jobs moved to dead-letter queue",
        ["job_type", "queue"],
    )
    JOBS_DURATION = Histogram(
        "finmind_job_duration_seconds",
        "Job execution duration",
        ["job_type"],
        buckets=[1, 5, 10, 30, 60, 120, 300],
    )
    QUEUE_DEPTH = Gauge(
        "finmind_queue_depth",
        "Current queue depth",
        ["queue"],
    )
    _METRICS_ENABLED = True
except ImportError:
    _METRICS_ENABLED = False
