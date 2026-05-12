"""Resilient background job system with retry and monitoring."""

import json
import time
import traceback
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from ..extensions import redis_client
import logging

logger = logging.getLogger("finmind.jobs")

QUEUE_KEY = "jobs:queue"
DEAD_LETTER_KEY = "jobs:dead_letter"
JOB_PREFIX = "jobs:status:"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class RetryPolicy:
    """Configurable retry policy with exponential backoff."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)


DEFAULT_RETRY_POLICY = RetryPolicy(max_retries=3, base_delay=2.0, max_delay=60.0)

# Registry of job handlers
_handlers: dict[str, Callable] = {}


def register_handler(name: str):
    """Decorator to register a job handler."""
    def decorator(fn: Callable):
        _handlers[name] = fn
        return fn
    return decorator


def enqueue(job_type: str, payload: dict, retry_policy: RetryPolicy | None = None) -> str:
    """Enqueue a job for background processing. Returns job_id."""
    job_id = str(uuid.uuid4())
    policy = retry_policy or DEFAULT_RETRY_POLICY

    job_data = {
        "id": job_id,
        "type": job_type,
        "payload": payload,
        "status": JobStatus.QUEUED,
        "attempt": 0,
        "max_retries": policy.max_retries,
        "base_delay": policy.base_delay,
        "max_delay": policy.max_delay,
        "created_at": datetime.utcnow().isoformat(),
        "error": None,
    }

    redis_client.set(f"{JOB_PREFIX}{job_id}", json.dumps(job_data), ex=86400 * 7)
    redis_client.lpush(QUEUE_KEY, json.dumps(job_data))
    logger.info("Job enqueued: id=%s type=%s", job_id, job_type)
    return job_id


def get_job_status(job_id: str) -> dict | None:
    """Get current status of a job."""
    raw = redis_client.get(f"{JOB_PREFIX}{job_id}")
    if not raw:
        return None
    return json.loads(raw)


def process_next() -> bool:
    """Process the next job in the queue. Returns True if a job was processed."""
    raw = redis_client.rpop(QUEUE_KEY)
    if not raw:
        return False

    job_data = json.loads(raw)
    job_id = job_data["id"]
    job_type = job_data["type"]

    handler = _handlers.get(job_type)
    if not handler:
        logger.error("No handler for job type: %s", job_type)
        job_data["status"] = JobStatus.DEAD
        job_data["error"] = f"No handler registered for type: {job_type}"
        _save_job(job_data)
        redis_client.lpush(DEAD_LETTER_KEY, json.dumps(job_data))
        return True

    job_data["status"] = JobStatus.RUNNING
    job_data["attempt"] += 1
    _save_job(job_data)

    try:
        handler(job_data["payload"])
        job_data["status"] = JobStatus.COMPLETED
        job_data["completed_at"] = datetime.utcnow().isoformat()
        _save_job(job_data)
        logger.info("Job completed: id=%s type=%s", job_id, job_type)
    except Exception as e:
        job_data["error"] = str(e)
        job_data["last_error_trace"] = traceback.format_exc()

        if job_data["attempt"] < job_data["max_retries"]:
            # Retry with backoff
            delay = job_data["base_delay"] * (2 ** (job_data["attempt"] - 1))
            delay = min(delay, job_data["max_delay"])
            job_data["status"] = JobStatus.QUEUED
            job_data["next_retry_at"] = (
                datetime.utcnow().isoformat()
            )
            _save_job(job_data)
            # Re-enqueue (in production, use delayed queue)
            redis_client.lpush(QUEUE_KEY, json.dumps(job_data))
            logger.warning(
                "Job failed, retrying: id=%s attempt=%d/%d delay=%.1fs error=%s",
                job_id, job_data["attempt"], job_data["max_retries"], delay, str(e),
            )
        else:
            # Move to dead letter queue
            job_data["status"] = JobStatus.DEAD
            _save_job(job_data)
            redis_client.lpush(DEAD_LETTER_KEY, json.dumps(job_data))
            logger.error(
                "Job exhausted retries: id=%s type=%s error=%s",
                job_id, job_type, str(e),
            )

    return True


def get_queue_stats() -> dict:
    """Get monitoring stats for the job queue."""
    return {
        "queue_length": redis_client.llen(QUEUE_KEY),
        "dead_letter_count": redis_client.llen(DEAD_LETTER_KEY),
    }


def get_dead_letter_jobs(limit: int = 20) -> list[dict]:
    """Get jobs in the dead letter queue."""
    raw_list = redis_client.lrange(DEAD_LETTER_KEY, 0, limit - 1)
    return [json.loads(r) for r in raw_list]


def retry_dead_letter_job(job_id: str) -> bool:
    """Retry a specific dead letter job."""
    job_data = get_job_status(job_id)
    if not job_data or job_data["status"] != JobStatus.DEAD:
        return False
    job_data["status"] = JobStatus.QUEUED
    job_data["attempt"] = 0
    job_data["error"] = None
    _save_job(job_data)
    redis_client.lpush(QUEUE_KEY, json.dumps(job_data))
    return True


def _save_job(job_data: dict):
    redis_client.set(
        f"{JOB_PREFIX}{job_data['id']}", json.dumps(job_data), ex=86400 * 7
    )
