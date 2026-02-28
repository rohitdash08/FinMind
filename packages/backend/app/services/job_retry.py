"""Resilient background job retry and monitoring.

Provides exponential backoff retry logic, job status tracking,
dead letter queue for failed jobs, and monitoring dashboard data.
"""

import time
import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"  # exhausted all retries


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 300.0,
        backoff_factor: float = 2.0,
        retry_on: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retry_on = retry_on

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)


class JobRecord:
    """Record of a job execution."""

    def __init__(self, job_id: str, name: str, args: tuple, kwargs: dict):
        self.job_id = job_id
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.status = JobStatus.PENDING
        self.attempts = 0
        self.max_attempts = 0
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.last_error = None
        self.error_history: List[dict] = []
        self.result = None
        self.duration_ms = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_error": self.last_error,
            "error_count": len(self.error_history),
            "duration_ms": self.duration_ms,
        }


class JobMonitor:
    """In-memory job monitoring and dead letter queue."""

    def __init__(self, max_history: int = 1000):
        self._jobs: Dict[str, JobRecord] = {}
        self._dead_letter: List[JobRecord] = []
        self._max_history = max_history

    def register(self, record: JobRecord):
        if len(self._jobs) >= self._max_history:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            del self._jobs[oldest.job_id]
        self._jobs[record.job_id] = record

    def get(self, job_id: str) -> Optional[JobRecord]:
        return self._jobs.get(job_id)

    def add_to_dead_letter(self, record: JobRecord):
        self._dead_letter.append(record)
        if len(self._dead_letter) > self._max_history:
            self._dead_letter = self._dead_letter[-self._max_history:]

    def stats(self) -> dict:
        jobs = list(self._jobs.values())
        by_status = {}
        for j in jobs:
            by_status[j.status.value] = by_status.get(j.status.value, 0) + 1

        successful = [j for j in jobs if j.status == JobStatus.SUCCESS and j.duration_ms]
        avg_duration = (
            sum(j.duration_ms for j in successful) / len(successful)
            if successful else 0
        )

        return {
            "total_jobs": len(jobs),
            "by_status": by_status,
            "dead_letter_count": len(self._dead_letter),
            "avg_duration_ms": round(avg_duration, 1),
            "retry_rate": f"{sum(1 for j in jobs if j.attempts > 1) / len(jobs) * 100:.1f}%"
            if jobs else "0%",
        }

    def recent(self, limit: int = 20, status: Optional[str] = None) -> List[dict]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        return [j.to_dict() for j in jobs[:limit]]

    def dead_letter_queue(self, limit: int = 20) -> List[dict]:
        return [j.to_dict() for j in self._dead_letter[-limit:]]


# Global monitor
_monitor = JobMonitor()


def get_monitor() -> JobMonitor:
    return _monitor


def with_retry(config: Optional[RetryConfig] = None):
    """Decorator for resilient job execution with retry."""
    if config is None:
        config = RetryConfig()

    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            job_id = str(uuid.uuid4())[:8]
            record = JobRecord(job_id, f.__name__, args, kwargs)
            record.max_attempts = config.max_retries + 1
            _monitor.register(record)

            for attempt in range(config.max_retries + 1):
                record.attempts = attempt + 1
                record.status = JobStatus.RUNNING if attempt == 0 else JobStatus.RETRYING
                record.started_at = datetime.utcnow()

                try:
                    start = time.time()
                    result = f(*args, **kwargs)
                    record.duration_ms = round((time.time() - start) * 1000, 1)
                    record.status = JobStatus.SUCCESS
                    record.completed_at = datetime.utcnow()
                    record.result = result
                    return result

                except config.retry_on as e:
                    error_info = {
                        "attempt": attempt + 1,
                        "error": str(e),
                        "type": type(e).__name__,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    record.error_history.append(error_info)
                    record.last_error = str(e)
                    logger.warning(
                        f"Job {f.__name__} attempt {attempt + 1} failed: {e}"
                    )

                    if attempt < config.max_retries:
                        delay = config.get_delay(attempt)
                        logger.info(f"Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        record.status = JobStatus.DEAD
                        record.completed_at = datetime.utcnow()
                        _monitor.add_to_dead_letter(record)
                        logger.error(
                            f"Job {f.__name__} exhausted {config.max_retries + 1} attempts"
                        )
                        raise

        return wrapper
    return decorator
