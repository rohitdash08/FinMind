"""Resilient background job retry & monitoring service."""

import time
import math
import logging
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("finmind.jobs")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"


class Job:
    """Represents a tracked background job."""

    def __init__(self, job_id: str, name: str):
        self.job_id = job_id
        self.name = name
        self.status = JobStatus.PENDING
        self.attempts = 0
        self.max_retries = 3
        self.last_error = None
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.result = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class JobManager:
    """Manages job execution with retry, monitoring, and dead letter queue."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self._jobs: dict[str, Job] = {}
        self._dead_letter: list[Job] = []
        self._stats = {
            "total_submitted": 0,
            "total_succeeded": 0,
            "total_failed": 0,
            "total_retries": 0,
        }

    def _compute_delay(self, attempt: int) -> float:
        """Exponential backoff with cap."""
        delay = self.base_delay * math.pow(self.backoff_factor, attempt)
        return min(delay, self.max_delay)

    def submit(self, job_id: str, name: str, func: Callable, *args: Any, **kwargs: Any) -> Job:
        """Submit a job for execution with retry logic."""
        job = Job(job_id, name)
        job.max_retries = self.max_retries
        self._jobs[job_id] = job
        self._stats["total_submitted"] += 1

        self._execute_with_retry(job, func, *args, **kwargs)
        return job

    def _execute_with_retry(self, job: Job, func: Callable, *args: Any, **kwargs: Any) -> None:
        """Execute a function with exponential backoff retry."""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        for attempt in range(self.max_retries + 1):
            job.attempts = attempt + 1
            try:
                job.result = func(*args, **kwargs)
                job.status = JobStatus.SUCCESS
                job.completed_at = datetime.utcnow()
                self._stats["total_succeeded"] += 1
                logger.info("Job %s succeeded on attempt %d", job.job_id, attempt + 1)
                return
            except Exception as exc:
                job.last_error = str(exc)
                logger.warning(
                    "Job %s failed attempt %d/%d: %s",
                    job.job_id, attempt + 1, self.max_retries + 1, exc,
                )
                if attempt < self.max_retries:
                    job.status = JobStatus.RETRYING
                    self._stats["total_retries"] += 1
                    delay = self._compute_delay(attempt)
                    time.sleep(delay)

        # Exhausted all retries -> dead letter
        job.status = JobStatus.DEAD
        job.completed_at = datetime.utcnow()
        self._dead_letter.append(job)
        self._stats["total_failed"] += 1
        logger.error("Job %s moved to dead letter queue after %d attempts", job.job_id, job.attempts)

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "active_jobs": sum(
                1 for j in self._jobs.values()
                if j.status in (JobStatus.RUNNING, JobStatus.RETRYING, JobStatus.PENDING)
            ),
            "dead_letter_count": len(self._dead_letter),
        }

    def get_recent_jobs(self, limit: int = 20) -> list[dict]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]

    def get_dead_letter_queue(self) -> list[dict]:
        return [j.to_dict() for j in self._dead_letter]

    def clear_dead_letter(self) -> int:
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count


# Global job manager instance
job_manager = JobManager()


def with_retry(
    max_retries: int = 3,
    base_delay: float = 0.1,
    backoff_factor: float = 2.0,
):
    """Decorator to add retry logic to any function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * math.pow(backoff_factor, attempt)
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
