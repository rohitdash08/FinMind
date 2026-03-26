"""Resilient background job manager with retry logic and monitoring.

Provides exponential backoff retries, dead-letter queue for permanently
failed jobs, circuit-breaker pattern for external services, and
Prometheus-compatible metrics for all job lifecycle events.
"""

import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from ..config import Settings
from ..extensions import db, redis_client
from ..models import JobExecution, JobStatus

logger = logging.getLogger("finmind.jobs")

# ---------------------------------------------------------------------------
# Configuration (loaded from Settings / environment variables)
# ---------------------------------------------------------------------------
_settings = Settings()
DEFAULT_MAX_RETRIES = _settings.job_max_retries
BASE_BACKOFF_SECONDS = _settings.job_base_backoff_seconds  # 5 min
BACKOFF_MULTIPLIER = _settings.job_backoff_multiplier
JITTER_FACTOR = _settings.job_jitter_factor

# Circuit-breaker defaults
CB_FAILURE_THRESHOLD = _settings.job_cb_failure_threshold
CB_RECOVERY_TIMEOUT = _settings.job_cb_recovery_timeout  # 5 min

# Redis key prefixes
REDIS_CB_PREFIX = "finmind:circuit_breaker:"
REDIS_DLQ_PREFIX = "finmind:dlq:"

# ---------------------------------------------------------------------------
# Job registry: maps job_type strings to handler callables
# ---------------------------------------------------------------------------
_job_registry: dict[str, Callable] = {}


def register_job(job_type: str):
    """Decorator to register a callable as a job handler."""

    def decorator(fn: Callable):
        _job_registry[job_type] = fn
        return fn

    return decorator


def get_handler(job_type: str) -> Callable | None:
    return _job_registry.get(job_type)


# ---------------------------------------------------------------------------
# Backoff calculation (pure function, easily testable)
# ---------------------------------------------------------------------------


def calculate_backoff(
    retry_count: int,
    base_seconds: int = BASE_BACKOFF_SECONDS,
    multiplier: float = BACKOFF_MULTIPLIER,
    jitter_factor: float = JITTER_FACTOR,
) -> float:
    """Calculate exponential backoff delay with jitter.

    Returns seconds to wait before the next retry.
    Formula: base * multiplier^retry_count * (1 +/- jitter)

    Example with defaults (base=300, mult=3):
        retry 0 -> ~300s  (5 min)
        retry 1 -> ~900s  (15 min)
        retry 2 -> ~2700s (45 min)
    """
    delay = base_seconds * (multiplier ** retry_count)
    jitter = delay * jitter_factor * (2 * random.random() - 1)
    return max(1.0, delay + jitter)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Redis-backed circuit breaker for external service calls.

    States: CLOSED (normal), OPEN (failing, reject calls),
    HALF_OPEN (testing recovery).
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = CB_FAILURE_THRESHOLD,
        recovery_timeout: int = CB_RECOVERY_TIMEOUT,
        redis_client_override=None,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._redis = redis_client_override or redis_client
        self._key = f"{REDIS_CB_PREFIX}{service_name}"

    def _get_state(self) -> dict:
        try:
            raw = self._redis.get(self._key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return {"state": self.CLOSED, "failure_count": 0, "last_failure_time": None}

    def _set_state(self, state: dict) -> None:
        try:
            self._redis.set(self._key, json.dumps(state), ex=self.recovery_timeout * 2)
        except Exception:
            logger.warning("Circuit breaker Redis write failed for %s", self.service_name)

    @property
    def state(self) -> str:
        s = self._get_state()
        if s["state"] == self.OPEN and s.get("last_failure_time"):
            elapsed = time.time() - s["last_failure_time"]
            if elapsed >= self.recovery_timeout:
                return self.HALF_OPEN
        return s["state"]

    def is_available(self) -> bool:
        current = self.state
        return current in (self.CLOSED, self.HALF_OPEN)

    def record_success(self) -> None:
        self._set_state(
            {"state": self.CLOSED, "failure_count": 0, "last_failure_time": None}
        )

    def record_failure(self) -> None:
        s = self._get_state()
        s["failure_count"] = s.get("failure_count", 0) + 1
        s["last_failure_time"] = time.time()
        if s["failure_count"] >= self.failure_threshold:
            s["state"] = self.OPEN
        self._set_state(s)

    def reset(self) -> None:
        try:
            self._redis.delete(self._key)
        except Exception:
            pass


# Shared circuit breakers for known external services
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(service_name: str) -> CircuitBreaker:
    if service_name not in _circuit_breakers:
        _circuit_breakers[service_name] = CircuitBreaker(service_name)
    return _circuit_breakers[service_name]


# ---------------------------------------------------------------------------
# Core job operations
# ---------------------------------------------------------------------------


def enqueue_job(
    job_type: str,
    payload: dict | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> JobExecution:
    """Create a new job execution record in PENDING state."""
    job = JobExecution(
        job_type=job_type,
        status=JobStatus.PENDING.value,
        payload=json.dumps(payload) if payload else None,
        max_retries=max_retries,
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job id=%s type=%s", job.id, job_type)
    return job


def execute_job(job: JobExecution, app=None) -> bool:
    """Execute a single job with error handling and retry scheduling.

    Returns True if the job completed successfully, False otherwise.
    """
    handler = get_handler(job.job_type)
    if handler is None:
        logger.error("No handler registered for job type=%s", job.job_type)
        _move_to_dead_letter(job, error="No handler registered")
        return False

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        payload = json.loads(job.payload) if job.payload else {}
        result = handler(payload)
        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        job.result = json.dumps(result) if result else None
        db.session.commit()
        logger.info("Job id=%s type=%s completed successfully", job.id, job.job_type)
        return True
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Job id=%s type=%s failed: %s (retry %d/%d)",
            job.id,
            job.job_type,
            error_msg,
            job.retry_count,
            job.max_retries,
        )
        return _handle_failure(job, error_msg)


def _handle_failure(job: JobExecution, error: str) -> bool:
    """Schedule retry or move to dead-letter queue."""
    job.last_error = error
    job.retry_count += 1

    if job.retry_count >= job.max_retries:
        _move_to_dead_letter(job, error)
        return False

    backoff = calculate_backoff(job.retry_count - 1)
    job.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff)
    job.status = JobStatus.PENDING.value
    db.session.commit()
    logger.info(
        "Job id=%s scheduled for retry at %s (attempt %d/%d)",
        job.id,
        job.next_retry_at.isoformat(),
        job.retry_count,
        job.max_retries,
    )
    return False


def _move_to_dead_letter(job: JobExecution, error: str) -> None:
    """Move job to DEAD state (dead-letter queue)."""
    job.status = JobStatus.DEAD.value
    job.last_error = error
    job.completed_at = datetime.utcnow()
    db.session.commit()

    # Also publish to Redis DLQ for external consumers
    try:
        dlq_entry = {
            "job_id": job.id,
            "job_type": job.job_type,
            "error": error,
            "retry_count": job.retry_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "dead_at": datetime.utcnow().isoformat(),
        }
        redis_client.lpush(
            f"{REDIS_DLQ_PREFIX}{job.job_type}",
            json.dumps(dlq_entry),
        )
    except Exception:
        logger.warning("Failed to push job id=%s to Redis DLQ", job.id)

    logger.error(
        "Job id=%s type=%s moved to dead-letter queue after %d attempts: %s",
        job.id,
        job.job_type,
        job.retry_count,
        error,
    )


# ---------------------------------------------------------------------------
# Retry processing (called by the scheduler)
# ---------------------------------------------------------------------------


def process_pending_retries() -> int:
    """Find and execute all jobs that are due for retry.

    Returns the number of jobs processed.
    """
    now = datetime.utcnow()
    pending = (
        db.session.query(JobExecution)
        .filter(
            JobExecution.status == JobStatus.PENDING.value,
            JobExecution.retry_count > 0,
            JobExecution.next_retry_at <= now,
        )
        .all()
    )
    processed = 0
    for job in pending:
        execute_job(job)
        processed += 1

    if processed:
        logger.info("Processed %d pending retries", processed)
    return processed


# ---------------------------------------------------------------------------
# Dead-letter queue management
# ---------------------------------------------------------------------------


def get_dead_letter_jobs(
    job_type: str | None = None, limit: int = 50
) -> list[JobExecution]:
    """Retrieve dead-letter jobs, optionally filtered by type."""
    q = db.session.query(JobExecution).filter(
        JobExecution.status == JobStatus.DEAD.value
    )
    if job_type:
        q = q.filter(JobExecution.job_type == job_type)
    return q.order_by(JobExecution.completed_at.desc()).limit(limit).all()


def retry_dead_letter_job(job_id: int) -> JobExecution | None:
    """Reset a dead-letter job for another attempt."""
    job = db.session.get(JobExecution, job_id)
    if not job or job.status != JobStatus.DEAD.value:
        return None

    job.status = JobStatus.PENDING.value
    job.retry_count = 0
    job.last_error = None
    job.next_retry_at = None
    job.started_at = None
    job.completed_at = None
    db.session.commit()
    logger.info("Reset dead-letter job id=%s for retry", job_id)
    return job


# ---------------------------------------------------------------------------
# Statistics & health
# ---------------------------------------------------------------------------


def get_job_stats() -> dict[str, Any]:
    """Aggregate job statistics by status and type."""
    from sqlalchemy import func

    rows = (
        db.session.query(
            JobExecution.job_type,
            JobExecution.status,
            func.count(JobExecution.id),
        )
        .group_by(JobExecution.job_type, JobExecution.status)
        .all()
    )
    stats: dict[str, dict] = {}
    total = 0
    for job_type, status, count in rows:
        if job_type not in stats:
            stats[job_type] = {}
        stats[job_type][status] = count
        total += count

    # Overall success rate
    completed = sum(
        s.get(JobStatus.COMPLETED.value, 0) for s in stats.values()
    )
    failed = sum(s.get(JobStatus.DEAD.value, 0) for s in stats.values())
    success_rate = (completed / (completed + failed) * 100) if (completed + failed) else 0.0

    return {
        "total_jobs": total,
        "success_rate": round(success_rate, 2),
        "by_type": stats,
    }


def get_health_status() -> dict[str, Any]:
    """Health check for the job system."""
    from sqlalchemy import func

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)

    # Count stuck jobs (RUNNING for more than 1 hour)
    stuck = (
        db.session.query(func.count(JobExecution.id))
        .filter(
            JobExecution.status == JobStatus.RUNNING.value,
            JobExecution.started_at < one_hour_ago,
        )
        .scalar()
    )

    # Count overdue retries
    overdue = (
        db.session.query(func.count(JobExecution.id))
        .filter(
            JobExecution.status == JobStatus.PENDING.value,
            JobExecution.retry_count > 0,
            JobExecution.next_retry_at < now - timedelta(minutes=10),
        )
        .scalar()
    )

    # Recent dead letters (last hour)
    recent_dead = (
        db.session.query(func.count(JobExecution.id))
        .filter(
            JobExecution.status == JobStatus.DEAD.value,
            JobExecution.completed_at >= one_hour_ago,
        )
        .scalar()
    )

    healthy = stuck == 0 and recent_dead < 10
    return {
        "healthy": healthy,
        "stuck_jobs": stuck or 0,
        "overdue_retries": overdue or 0,
        "recent_dead_letters": recent_dead or 0,
        "checked_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Reminder dispatch integration
# ---------------------------------------------------------------------------


def dispatch_reminders(candidates, sender_fn, now=None):
    """Pure function: dispatch due reminders with job tracking.

    Args:
        candidates: list of Reminder objects to process
        sender_fn: callable(reminder) -> bool
        now: override for current time (testing)

    Returns:
        dict with sent_count, failed_count, and details
    """
    if now is None:
        now = datetime.utcnow()

    sent = 0
    failed = 0
    details = []

    for reminder in candidates:
        try:
            success = sender_fn(reminder)
            if success:
                reminder.sent = True
                sent += 1
                details.append({"id": reminder.id, "status": "sent"})
            else:
                failed += 1
                details.append({"id": reminder.id, "status": "send_failed"})
        except Exception as exc:
            failed += 1
            details.append(
                {"id": reminder.id, "status": "error", "error": str(exc)}
            )

    return {"sent_count": sent, "failed_count": failed, "details": details}
