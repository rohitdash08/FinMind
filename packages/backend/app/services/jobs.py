"""
Background job retry & monitoring module.

Provides a generic AsyncJob model, a robust job runner with exponential
backoff retry, and Flask CLI / API endpoints for monitoring.
"""
import functools
import logging
import random
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from ..extensions import db

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class AsyncJob(db.Model):
    """Persistent record of an async background job."""

    __tablename__ = "async_jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(100), nullable=False, index=True, doc="e.g. send_reminder, generate_digest")
    status = Column(String(20), default=JobStatus.PENDING.value, nullable=False, index=True)
    payload = Column(Text, nullable=True, doc="JSON-serialized input data")
    result = Column(Text, nullable=True, doc="JSON-serialized output / error info")
    attempt = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime(timezone=False), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    duration_ms = Column(Float, nullable=True)

    def mark_running(self):
        self.status = JobStatus.RUNNING.value
        self.attempt += 1
        self.started_at = datetime.utcnow()
        db.session.commit()

    def mark_success(self, result_data: str = ""):
        self.status = JobStatus.SUCCESS.value
        self.result = result_data
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.next_retry_at = None
        db.session.commit()

    def mark_failed(self, error: str, schedule_retry: bool = True):
        self.last_error = error
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000

        if schedule_retry and self.attempt < self.max_attempts:
            self.status = JobStatus.RETRYING.value
            # Exponential backoff with jitter: base 30s, double each attempt, ±20% jitter
            delay = 30 * (2 ** (self.attempt - 1))
            jitter = random.uniform(0.8, 1.2)
            self.next_retry_at = datetime.utcnow() + timedelta(seconds=int(delay * jitter))
        else:
            self.status = JobStatus.FAILED.value
            self.next_retry_at = None

        db.session.commit()

    def cancel(self):
        self.status = JobStatus.CANCELLED.value
        self.next_retry_at = None
        db.session.commit()

    def to_dict(self):
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "duration_ms": self.duration_ms,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ─── Runner ───────────────────────────────────────────────────────


class JobRunner:
    """Generic synchronous job runner with retry support."""

    def __init__(self, handler: Callable, max_attempts: int = 3):
        self.handler = handler
        self.max_attempts = max_attempts

    def run(self, payload: str = "") -> AsyncJob:
        """Execute the handler in-process, wrapping with retry logic."""
        job = AsyncJob(
            job_type=self.handler.__name__,
            status=JobStatus.PENDING.value,
            payload=payload,
            max_attempts=self.max_attempts,
        )
        db.session.add(job)
        db.session.commit()

        try:
            job.mark_running()
            result_data = self.handler(payload)
            job.mark_success(result_data)
        except Exception as exc:
            logger.warning("Job %s attempt %d/%d failed: %s",
                           job.id, job.attempt, job.max_attempts, exc)
            job.mark_failed(str(exc), schedule_retry=True)
        return job


# ─── Retry daemon ─────────────────────────────────────────────────


def process_retry_queue(max_jobs: int = 10) -> int:
    """Pick up to *max_jobs* retry-eligible jobs and re-run them."""
    now = datetime.utcnow()
    due = AsyncJob.query.filter(
        AsyncJob.status == JobStatus.RETRYING.value,
        AsyncJob.next_retry_at <= now,
    ).order_by(AsyncJob.next_retry_at.asc()).limit(max_jobs).all()

    for job in due:
        try:
            runner = JobRunner(_handler_registry.get(job.job_type))
            if runner.handler is None:
                job.mark_failed(f"No handler registered for {job.job_type}", schedule_retry=False)
                continue
            job.mark_running()
            result = runner.handler(job.payload or "")
            job.mark_success(result)
        except Exception as exc:
            job.mark_failed(str(exc), schedule_retry=True)

    return len(due)


_handler_registry: dict = {}


def register_handler(name: str):
    """Decorator: register a callable as a named job handler."""
    def wrapper(fn):
        _handler_registry[name] = fn
        @functools.wraps(fn)
        def wrapped(*a, **kw):
            return fn(*a, **kw)
        return wrapped
    return wrapper
