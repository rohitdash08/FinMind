"""Resilient job retry engine with exponential backoff.

Wraps any callable into a tracked, retryable background job with:
- Exponential backoff (base * 2^attempt) with jitter
- Per-job execution logging to DB
- Dead-letter status after max retries exhausted
- Redis-backed real-time status cache for fast polling
- Pluggable alert hooks for failed/dead jobs
"""

import json
import logging
import math
import random
import time
import traceback
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

from ..extensions import db, redis_client
from ..models.job_execution import JobExecution, JobStatus

logger = logging.getLogger("finmind.jobs")

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 10
DEFAULT_BACKOFF_MAX_SECONDS = 600  # 10 min ceiling
JITTER_FACTOR = 0.25  # ±25 % jitter

# Redis key prefix for live status
_REDIS_PREFIX = "finmind:job:"

# ---------------------------------------------------------------------------
# Alert callbacks (pluggable)
# ---------------------------------------------------------------------------
_alert_callbacks: list[Callable[[JobExecution], None]] = []


def register_alert_callback(fn: Callable[[JobExecution], None]):
    """Register a callback invoked when a job fails or becomes DEAD."""
    _alert_callbacks.append(fn)


def _fire_alerts(execution: JobExecution):
    for cb in _alert_callbacks:
        try:
            cb(execution)
        except Exception:
            logger.exception("Alert callback error for job %s", execution.job_id)


# ---------------------------------------------------------------------------
# Backoff calculator
# ---------------------------------------------------------------------------
def compute_backoff(
    attempt: int,
    base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    cap: float = DEFAULT_BACKOFF_MAX_SECONDS,
) -> float:
    """Exponential backoff with jitter.  attempt is 0-indexed retry number."""
    delay = min(base * (2**attempt), cap)
    jitter = delay * JITTER_FACTOR * (2 * random.random() - 1)
    return max(0, delay + jitter)


# ---------------------------------------------------------------------------
# Core execution wrapper
# ---------------------------------------------------------------------------
def execute_with_retry(
    fn: Callable[..., Any],
    args: tuple = (),
    kwargs: dict | None = None,
    job_name: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    app=None,
) -> JobExecution:
    """Run *fn* with automatic retry + tracking.

    This is the **synchronous** entry point.  For APScheduler integration
    the ``resilient_job`` decorator is preferred.

    Returns the final :class:`JobExecution` row.
    """
    kwargs = kwargs or {}
    job_id = f"{job_name or fn.__name__}_{uuid.uuid4().hex[:12]}"
    resolved_name = job_name or fn.__name__

    ctx = app.app_context() if app else _noop_ctx()

    with ctx:
        execution = JobExecution(
            job_id=job_id,
            job_name=resolved_name,
            status=JobStatus.PENDING,
            attempt=1,
            max_retries=max_retries,
        )
        db.session.add(execution)
        db.session.commit()
        _cache_status(execution)

        for attempt in range(max_retries + 1):
            execution.attempt = attempt + 1
            execution.status = JobStatus.RUNNING
            execution.started_at = datetime.utcnow()
            execution.next_retry_at = None
            db.session.commit()
            _cache_status(execution)

            t0 = time.monotonic()
            try:
                fn(*args, **kwargs)
                elapsed = int((time.monotonic() - t0) * 1000)
                execution.status = JobStatus.SUCCESS
                execution.finished_at = datetime.utcnow()
                execution.duration_ms = elapsed
                execution.error_message = None
                execution.error_traceback = None
                db.session.commit()
                _cache_status(execution)
                logger.info(
                    "Job %s succeeded on attempt %d (%d ms)",
                    job_id,
                    attempt + 1,
                    elapsed,
                )
                return execution
            except Exception as exc:
                elapsed = int((time.monotonic() - t0) * 1000)
                execution.duration_ms = elapsed
                execution.error_message = str(exc)[:2000]
                execution.error_traceback = traceback.format_exc()[:4000]
                execution.finished_at = datetime.utcnow()

                if attempt < max_retries:
                    delay = compute_backoff(attempt, backoff_base)
                    execution.status = JobStatus.RETRYING
                    execution.next_retry_at = datetime.utcnow() + timedelta(
                        seconds=delay
                    )
                    db.session.commit()
                    _cache_status(execution)
                    _fire_alerts(execution)
                    logger.warning(
                        "Job %s attempt %d failed (%s), retrying in %.1fs",
                        job_id,
                        attempt + 1,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    execution.status = JobStatus.DEAD
                    db.session.commit()
                    _cache_status(execution)
                    _fire_alerts(execution)
                    logger.error(
                        "Job %s DEAD after %d attempts: %s",
                        job_id,
                        max_retries + 1,
                        exc,
                    )
                    return execution

    return execution  # unreachable, but keeps type-checkers happy


# ---------------------------------------------------------------------------
# Decorator for APScheduler jobs
# ---------------------------------------------------------------------------
def resilient_job(
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    job_name: str | None = None,
):
    """Decorator that wraps an APScheduler job function with retry logic.

    Usage::

        @resilient_job(max_retries=5, backoff_base=15)
        def my_scheduled_task():
            ...
    """

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import current_app

            app = current_app._get_current_object()  # type: ignore[attr-defined]
            return execute_with_retry(
                fn,
                args=args,
                kwargs=kwargs,
                job_name=job_name or fn.__name__,
                max_retries=max_retries,
                backoff_base=backoff_base,
                app=app,
            )

        # Preserve original name so APScheduler id works
        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Redis status cache helpers
# ---------------------------------------------------------------------------
def _cache_status(execution: JobExecution, ttl: int = 86400):
    """Push lightweight status into Redis for fast API reads."""
    try:
        key = f"{_REDIS_PREFIX}{execution.job_id}"
        data = {
            "id": execution.id,
            "job_id": execution.job_id,
            "job_name": execution.job_name,
            "status": execution.status.value,
            "attempt": execution.attempt,
            "max_retries": execution.max_retries,
            "error_message": execution.error_message or "",
            "updated_at": datetime.utcnow().isoformat(),
        }
        redis_client.set(key, json.dumps(data), ex=ttl)
    except Exception:
        logger.debug("Redis cache write failed for %s", execution.job_id)


def get_cached_status(job_id: str) -> dict | None:
    """Read cached status from Redis (or None)."""
    try:
        raw = redis_client.get(f"{_REDIS_PREFIX}{job_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------
def get_recent_executions(
    limit: int = 50,
    status: Optional[str] = None,
    job_name: Optional[str] = None,
) -> list[JobExecution]:
    """Return recent job executions, optionally filtered."""
    q = JobExecution.query.order_by(JobExecution.created_at.desc())
    if status:
        try:
            q = q.filter(JobExecution.status == JobStatus(status))
        except ValueError:
            pass
    if job_name:
        q = q.filter(JobExecution.job_name == job_name)
    return q.limit(limit).all()


def get_job_stats() -> dict:
    """Aggregate counts by status for the dashboard summary."""
    rows = (
        db.session.query(JobExecution.status, db.func.count(JobExecution.id))
        .group_by(JobExecution.status)
        .all()
    )
    stats = {s.value: 0 for s in JobStatus}
    for status, count in rows:
        key = status.value if isinstance(status, JobStatus) else status
        stats[key] = count
    stats["total"] = sum(stats.values())
    return stats


# ---------------------------------------------------------------------------
# Noop context manager
# ---------------------------------------------------------------------------
class _noop_ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass
