"""
Background job system with retry logic, monitoring, and dead letter queue.
Uses Redis as the job queue backend.
"""

import json
import uuid
import time
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from redis.exceptions import RedisError

from ..extensions import redis_client

logger = logging.getLogger("finmind.jobs")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD = "DEAD"


class RetryPolicy:
    """Configurable retry policy with exponential backoff."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: float = 5.0,
        max_delay_seconds: float = 300.0,
        backoff_multiplier: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.backoff_multiplier = backoff_multiplier

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt (0-indexed)."""
        delay = self.base_delay_seconds * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_seconds)


# Default retry policy
DEFAULT_RETRY_POLICY = RetryPolicy()

# Redis key prefixes
QUEUE_KEY = "finmind:jobs:queue"
PROCESSING_KEY = "finmind:jobs:processing"
DEAD_LETTER_KEY = "finmind:jobs:dead"
JOB_PREFIX = "finmind:job:"
HISTORY_PREFIX = "finmind:jobs:history:"


def enqueue(
    task_name: str,
    payload: dict[str, Any],
    retry_policy: Optional[RetryPolicy] = None,
    user_id: Optional[int] = None,
) -> str:
    """Add a job to the queue. Returns job ID."""
    job_id = str(uuid.uuid4())
    policy = retry_policy or DEFAULT_RETRY_POLICY

    job = {
        "id": job_id,
        "task_name": task_name,
        "payload": json.dumps(payload),
        "status": JobStatus.PENDING.value,
        "user_id": user_id,
        "attempt": 0,
        "max_retries": policy.max_retries,
        "base_delay": policy.base_delay_seconds,
        "max_delay": policy.max_delay_seconds,
        "backoff_multiplier": policy.backoff_multiplier,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "finished_at": None,
        "error": None,
    }

    try:
        pipe = redis_client.pipeline()
        pipe.hset(f"{JOB_PREFIX}{job_id}", mapping=job)
        pipe.rpush(QUEUE_KEY, job_id)
        pipe.execute()
        logger.info("Job %s enqueued: %s", job_id, task_name)
    except RedisError as e:
        logger.error("Failed to enqueue job %s: %s", job_id, e)
        raise

    return job_id


def dequeue(timeout: float = 5.0) -> Optional[dict]:
    """Get next job from queue (blocking). Returns job dict or None."""
    try:
        result = redis_client.blpop(QUEUE_KEY, timeout=int(timeout))
        if not result:
            return None
        _, job_id = result
        job_id = str(job_id)

        job_data = redis_client.hgetall(f"{JOB_PREFIX}{job_id}")
        if not job_data:
            return None

        # Mark as processing
        now = datetime.utcnow().isoformat()
        updates = {
            "status": JobStatus.RUNNING.value,
            "started_at": now,
            "updated_at": now,
        }
        redis_client.hset(f"{JOB_PREFIX}{job_id}", mapping=updates)
        redis_client.sadd(PROCESSING_KEY, job_id)

        job_data.update(updates)
        return _deserialize_job(job_data)
    except RedisError as e:
        logger.error("Failed to dequeue: %s", e)
        return None


def mark_success(job_id: str) -> None:
    """Mark job as succeeded."""
    now = datetime.utcnow().isoformat()
    try:
        redis_client.hset(
            f"{JOB_PREFIX}{job_id}",
            mapping={
                "status": JobStatus.SUCCEEDED.value,
                "finished_at": now,
                "updated_at": now,
            },
        )
        redis_client.srem(PROCESSING_KEY, job_id)
        _add_to_history(job_id, JobStatus.SUCCEEDED)
        logger.info("Job %s succeeded", job_id)
    except RedisError as e:
        logger.error("Failed to mark job %s as succeeded: %s", job_id, e)


def mark_failed(job_id: str, error: str) -> None:
    """Mark job as failed. Will retry or move to dead letter queue."""
    try:
        job_data = redis_client.hgetall(f"{JOB_PREFIX}{job_id}")
        if not job_data:
            return

        attempt = int(job_data.get("attempt", 0)) + 1
        max_retries = int(job_data.get("max_retries", 3))

        now = datetime.utcnow().isoformat()

        if attempt <= max_retries:
            # Retry with exponential backoff
            base_delay = float(job_data.get("base_delay", 5))
            max_delay = float(job_data.get("max_delay", 300))
            multiplier = float(job_data.get("backoff_multiplier", 2))
            delay = min(base_delay * (multiplier ** (attempt - 1)), max_delay)

            redis_client.hset(
                f"{JOB_PREFIX}{job_id}",
                mapping={
                    "status": JobStatus.RETRYING.value,
                    "attempt": attempt,
                    "error": error[:500],
                    "updated_at": now,
                },
            )
            # Re-queue after delay (simple approach: immediate re-queue, worker checks timing)
            redis_client.rpush(QUEUE_KEY, job_id)
            logger.info(
                "Job %s retrying (attempt %d/%d, delay=%.1fs): %s",
                job_id, attempt, max_retries, delay, error,
            )
        else:
            # Max retries exceeded — move to dead letter queue
            redis_client.hset(
                f"{JOB_PREFIX}{job_id}",
                mapping={
                    "status": JobStatus.DEAD.value,
                    "error": error[:500],
                    "finished_at": now,
                    "updated_at": now,
                },
            )
            redis_client.srem(PROCESSING_KEY, job_id)
            redis_client.rpush(DEAD_LETTER_KEY, job_id)
            _add_to_history(job_id, JobStatus.DEAD)
            logger.error("Job %s moved to dead letter queue: %s", job_id, error)
    except RedisError as e:
        logger.error("Failed to process failure for job %s: %s", job_id, e)


def get_job(job_id: str) -> Optional[dict]:
    """Get job details by ID."""
    try:
        job_data = redis_client.hgetall(f"{JOB_PREFIX}{job_id}")
        if not job_data:
            return None
        return _deserialize_job(job_data)
    except RedisError:
        return None


def get_job_history(user_id: Optional[int] = None, limit: int = 50) -> list[dict]:
    """Get job execution history, optionally filtered by user."""
    try:
        # Scan recent jobs
        keys = redis_client.keys(f"{JOB_PREFIX}*")
        jobs = []
        for key in keys[:limit * 2]:
            job_data = redis_client.hgetall(key)
            if job_data:
                job = _deserialize_job(job_data)
                if user_id is None or job.get("user_id") == str(user_id):
                    jobs.append(job)
        # Sort by updated_at desc
        jobs.sort(key=lambda j: j.get("updated_at", ""), reverse=True)
        return jobs[:limit]
    except RedisError:
        return []


def get_stats() -> dict:
    """Get job queue statistics."""
    try:
        queue_len = redis_client.llen(QUEUE_KEY)
        processing_len = redis_client.scard(PROCESSING_KEY)
        dead_len = redis_client.llen(DEAD_LETTER_KEY)

        # Count by status
        keys = redis_client.keys(f"{JOB_PREFIX}*")
        status_counts = {s.value: 0 for s in JobStatus}
        for key in keys:
            status = redis_client.hget(key, "status")
            if status:
                status = status if isinstance(status, str) else status.decode()
                status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "queue_length": queue_len,
            "processing": processing_len,
            "dead_letter": dead_len,
            "total_jobs": len(keys),
            "by_status": status_counts,
        }
    except RedisError:
        return {"error": "redis unavailable"}


def retry_dead_job(job_id: str) -> bool:
    """Re-queue a dead letter job for another attempt."""
    try:
        job_data = redis_client.hgetall(f"{JOB_PREFIX}{job_id}")
        if not job_data:
            return False
        redis_client.hset(
            f"{JOB_PREFIX}{job_id}",
            mapping={
                "status": JobStatus.PENDING.value,
                "attempt": 0,
                "error": None,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        redis_client.rpush(QUEUE_KEY, job_id)
        # Remove from dead letter
        redis_client.lrem(DEAD_LETTER_KEY, 0, job_id)
        logger.info("Dead job %s re-queued", job_id)
        return True
    except RedisError:
        return False


def _add_to_history(job_id: str, status: JobStatus) -> None:
    """Add job to completion history."""
    try:
        entry = json.dumps({
            "job_id": job_id,
            "status": status.value,
            "timestamp": datetime.utcnow().isoformat(),
        })
        redis_client.lpush(f"{HISTORY_PREFIX}all", entry)
        redis_client.ltrim(f"{HISTORY_PREFIX}all", 0, 999)  # Keep last 1000
    except RedisError:
        pass


def _deserialize_job(data: dict) -> dict:
    """Convert Redis hash data to proper types."""
    return {
        "id": data.get("id", ""),
        "task_name": data.get("task_name", ""),
        "payload": json.loads(data.get("payload", "{}")) if data.get("payload") and data["payload"].startswith("{") else data.get("payload", {}),
        "status": data.get("status", "UNKNOWN"),
        "user_id": data.get("user_id"),
        "attempt": int(data.get("attempt", 0)),
        "max_retries": int(data.get("max_retries", 3)),
        "error": data.get("error"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
    }
