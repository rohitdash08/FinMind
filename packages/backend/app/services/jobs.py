"""Background job queue with retry logic for FinMind.

Uses Redis as a lightweight job queue with configurable retry
strategies, exponential backoff, and dead-letter handling.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from ..extensions import redis_client

logger = logging.getLogger("finmind.jobs")

# Redis key prefixes
QUEUE_PREFIX = "finmind:jobs:queue:"
RUNNING_PREFIX = "finmind:jobs:running:"
DEAD_LETTER_PREFIX = "finmind:jobs:dead:"
SCHEDULE_PREFIX = "finmind:jobs:schedule:"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"


@dataclass
class RetryPolicy:
    """Configurable retry policy for background jobs."""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_multiplier: float = 2.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate exponential backoff delay for a given attempt."""
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_seconds)


DEFAULT_RETRY_POLICY = RetryPolicy()


@dataclass
class Job:
    """A background job with retry support."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    payload: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    last_error: str | None = None
    scheduled_at: str | None = None
    retry_policy: dict = field(default_factory=lambda: asdict(DEFAULT_RETRY_POLICY))

    @property
    def retry_count(self) -> int:
        return max(0, self.attempts - 1)

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_retries

    def next_delay(self) -> float:
        """Calculate delay before next retry."""
        policy = RetryPolicy(**self.retry_policy)
        return policy.delay_for_attempt(self.attempts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "last_error": self.last_error,
            "scheduled_at": self.scheduled_at,
            "retry_policy": self.retry_policy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        data = dict(data)
        if "status" in data and isinstance(data["status"], str):
            data["status"] = JobStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Job Handlers Registry ─────────────────────────────────────────────

_job_handlers: dict[str, Callable[[dict], Any]] = {}


def register_job_handler(job_type: str, handler: Callable[[dict], Any]):
    """Register a handler function for a job type."""
    _job_handlers[job_type] = handler
    logger.info("Registered job handler: %s", job_type)


def get_job_handler(job_type: str) -> Callable[[dict], Any] | None:
    return _job_handlers.get(job_type)


# ── Queue Operations ──────────────────────────────────────────────────

def enqueue(
    job_type: str,
    payload: dict,
    max_retries: int = 3,
    retry_policy: RetryPolicy | None = None,
    scheduled_at: datetime | None = None,
) -> Job:
    """Enqueue a new background job.

    Args:
        job_type: Type of job (must have a registered handler).
        payload: Job-specific data passed to the handler.
        max_retries: Maximum number of retry attempts.
        retry_policy: Custom retry policy (uses default if None).
        scheduled_at: Optional future time to execute the job.

    Returns:
        The created Job object.
    """
    policy = retry_policy or DEFAULT_RETRY_POLICY
    job = Job(
        type=job_type,
        payload=payload,
        max_retries=max_retries,
        retry_policy=asdict(policy),
        scheduled_at=scheduled_at.isoformat() if scheduled_at else None,
    )

    queue_key = f"{QUEUE_PREFIX}{job_type}"
    redis_client.rpush(queue_key, json.dumps(job.to_dict()))

    if scheduled_at:
        schedule_key = f"{SCHEDULE_PREFIX}{job.id}"
        redis_client.setex(
            schedule_key,
            int((scheduled_at - datetime.now(timezone.utc())).total_seconds()) + 60,
            json.dumps(job.to_dict()),
        )

    logger.info(
        "Enqueued job id=%s type=%s retries=%d",
        job.id, job_type, max_retries,
    )
    return job


def dequeue(job_type: str, timeout: float = 0) -> Job | None:
    """Dequeue the next pending job of the given type.

    Returns None if no jobs are available.
    """
    queue_key = f"{QUEUE_PREFIX}{job_type}"
    result = redis_client.lpop(queue_key)
    if not result:
        return None

    job = Job.from_dict(json.loads(result))
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = datetime.now(timezone.utc).isoformat()

    # Track as running
    running_key = f"{RUNNING_PREFIX}{job.id}"
    redis_client.setex(running_key, 300, json.dumps(job.to_dict()))

    return job


def mark_completed(job: Job):
    """Mark a job as successfully completed."""
    job.status = JobStatus.COMPLETED
    job.completed_at = datetime.now(timezone.utc).isoformat()

    running_key = f"{RUNNING_PREFIX}{job.id}"
    redis_client.delete(running_key)

    logger.info("Job completed id=%s type=%s", job.id, job.type)


def mark_failed(job: Job, error: str) -> Job:
    """Mark a job as failed and schedule retry if possible.

    Returns the updated job (either retried or dead-lettered).
    """
    job.last_error = error[:500]  # Truncate long errors

    if job.can_retry:
        job.status = JobStatus.RETRYING
        delay = job.next_delay()

        # Re-enqueue with delay (simplified: re-push to queue)
        queue_key = f"{QUEUE_PREFIX}{job.type}"
        job.status = JobStatus.PENDING
        redis_client.rpush(queue_key, json.dumps(job.to_dict()))

        running_key = f"{RUNNING_PREFIX}{job.id}"
        redis_client.delete(running_key)

        logger.warning(
            "Job failed, retrying id=%s type=%s attempt=%d/%d next_delay=%.1fs error=%s",
            job.id, job.type, job.attempts, job.max_retries, delay, error[:100],
        )
    else:
        # Max retries exceeded → dead letter queue
        job.status = JobStatus.DEAD
        dead_key = f"{DEAD_LETTER_PREFIX}{job.type}"
        redis_client.rpush(dead_key, json.dumps(job.to_dict()))

        running_key = f"{RUNNING_PREFIX}{job.id}"
        redis_client.delete(running_key)

        logger.error(
            "Job dead-lettered id=%s type=%s attempts=%d error=%s",
            job.id, job.type, job.attempts, error[:200],
        )

    return job


def process_next(job_type: str) -> Job | None:
    """Process the next job in the queue with automatic retry handling.

    Returns the completed/failed job, or None if queue is empty.
    """
    job = dequeue(job_type)
    if not job:
        return None

    handler = get_job_handler(job.type)
    if not handler:
        mark_failed(job, f"No handler registered for job type: {job.type}")
        return job

    try:
        handler(job.payload)
        mark_completed(job)
    except Exception as exc:
        mark_failed(job, str(exc))

    return job


def get_dead_letters(job_type: str, limit: int = 50) -> list[Job]:
    """Retrieve dead-lettered jobs for inspection."""
    dead_key = f"{DEAD_LETTER_PREFIX}{job_type}"
    items = redis_client.lrange(dead_key, 0, limit - 1)
    return [Job.from_dict(json.loads(item)) for item in items]


def purge_dead_letters(job_type: str) -> int:
    """Remove all dead-lettered jobs for a type. Returns count purged."""
    dead_key = f"{DEAD_LETTER_PREFIX}{job_type}"
    count = redis_client.llen(dead_key)
    redis_client.delete(dead_key)
    return count


def retry_dead_letter(job_id: str, job_type: str) -> Job | None:
    """Re-queue a specific dead-lettered job for retry."""
    dead_key = f"{DEAD_LETTER_PREFIX}{job_type}"
    items = redis_client.lrange(dead_key, 0, -1)
    for raw in items:
        job = Job.from_dict(json.loads(raw))
        if job.id == job_id:
            redis_client.lrem(dead_key, 1, raw)
            job.status = JobStatus.PENDING
            job.attempts = 0
            job.last_error = None
            queue_key = f"{QUEUE_PREFIX}{job_type}"
            redis_client.rpush(queue_key, json.dumps(job.to_dict()))
            logger.info("Re-queued dead letter id=%s type=%s", job.id, job_type)
            return job
    return None


def get_queue_stats(job_type: str) -> dict:
    """Get statistics for a job type queue."""
    queue_key = f"{QUEUE_PREFIX}{job_type}"
    dead_key = f"{DEAD_LETTER_PREFIX}{job_type}"
    return {
        "job_type": job_type,
        "pending": redis_client.llen(queue_key),
        "dead_letters": redis_client.llen(dead_key),
    }
