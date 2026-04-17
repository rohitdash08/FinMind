import time
import json
import logging
import functools
from datetime import datetime, timedelta
from typing import Callable, Any
from ..extensions import db, redis_client

logger = logging.getLogger("finmind.jobs")

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAYS = [1, 5, 30]  # seconds
JOB_STATUS_KEY = "finmind:jobs:{job_id}"
JOB_QUEUE_KEY = "finmind:job_queue"


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead_letter"


class JobRecord:
    """Track job execution state in Redis."""

    def __init__(self, job_id, func_name, args=None):
        self.job_id = job_id
        self.func_name = func_name
        self.args = args or {}
        self.status = JobStatus.PENDING
        self.attempts = 0
        self.max_retries = DEFAULT_MAX_RETRIES
        self.created_at = datetime.utcnow().isoformat()
        self.last_error = None
        self.completed_at = None
        self.next_retry_at = None

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "func_name": self.func_name,
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "last_error": self.last_error,
            "completed_at": self.completed_at,
            "next_retry_at": self.next_retry_at,
        }

    def save(self):
        key = JOB_STATUS_KEY.format(job_id=self.job_id)
        try:
            redis_client.setex(key, 86400, json.dumps(self.to_dict()))
        except Exception as e:
            logger.warning("Failed to save job state: %s", e)

    @classmethod
    def load(cls, job_id):
        key = JOB_STATUS_KEY.format(job_id=job_id)
        try:
            data = redis_client.get(key)
            if data:
                d = json.loads(data)
                r = cls(d["job_id"], d["func_name"])
                r.status = d["status"]
                r.attempts = d["attempts"]
                r.max_retries = d.get("max_retries", DEFAULT_MAX_RETRIES)
                r.created_at = d["created_at"]
                r.last_error = d.get("last_error")
                r.completed_at = d.get("completed_at")
                r.next_retry_at = d.get("next_retry_at")
                return r
        except Exception as e:
            logger.warning("Failed to load job state: %s", e)
        return None


def retry_on_failure(
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delays: list = None,
    job_id: str = None,
):
    """Decorator for resilient job execution with exponential backoff retry."""
    delays = retry_delays or DEFAULT_RETRY_DELAYS

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            jid = job_id or f"{func.__name__}:{int(time.time()*1000)}"
            record = JobRecord(jid, func.__name__)
            record.max_retries = max_retries
            record.save()

            for attempt in range(max_retries + 1):
                record.attempts = attempt + 1
                record.status = JobStatus.RUNNING if attempt == 0 else JobStatus.RETRYING
                record.save()

                try:
                    result = func(*args, **kwargs)
                    record.status = JobStatus.SUCCESS
                    record.completed_at = datetime.utcnow().isoformat()
                    record.save()
                    logger.info("Job %s succeeded on attempt %d", jid, attempt + 1)
                    return result

                except Exception as e:
                    record.last_error = str(e)[:500]
                    logger.warning(
                        "Job %s attempt %d/%d failed: %s",
                        jid, attempt + 1, max_retries + 1, e,
                    )

                    if attempt < max_retries:
                        delay = delays[min(attempt, len(delays) - 1)]
                        record.next_retry_at = (
                            datetime.utcnow() + timedelta(seconds=delay)
                        ).isoformat()
                        record.status = JobStatus.RETRYING
                        record.save()
                        time.sleep(delay)
                    else:
                        record.status = JobStatus.DEAD
                        record.completed_at = datetime.utcnow().isoformat()
                        record.save()
                        logger.error(
                            "Job %s exhausted retries, moved to dead letter", jid
                        )

            return None

        return wrapper
    return decorator


def get_job_status(job_id: str) -> dict | None:
    """Get current status of a job."""
    record = JobRecord.load(job_id)
    return record.to_dict() if record else None


def get_failed_jobs(limit: int = 50) -> list:
    """List jobs in dead letter queue."""
    dead_jobs = []
    try:
        keys = redis_client.keys("finmind:jobs:*")
        for key in keys[:limit * 2]:
            data = redis_client.get(key)
            if data:
                d = json.loads(data)
                if d.get("status") == JobStatus.DEAD:
                    dead_jobs.append(d)
    except Exception as e:
        logger.warning("Failed to list dead jobs: %s", e)
    return dead_jobs[:limit]


def retry_dead_job(job_id: str) -> bool:
    """Manually retry a dead letter job."""
    record = JobRecord.load(job_id)
    if not record or record.status != JobStatus.DEAD:
        return False
    record.status = JobStatus.PENDING
    record.attempts = 0
    record.last_error = None
    record.completed_at = None
    record.save()
    return True
