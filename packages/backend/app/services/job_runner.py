"""
Resilient background job runner with retry and exponential backoff.

Provides a generic retry mechanism for async jobs (reminders, notifications, etc.)
with configurable max retries, exponential backoff, dead-letter tracking, and
monitoring endpoints.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from ..extensions import db
from ..models import BackgroundJob, JobStatus

logger = logging.getLogger("finmind.job_runner")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """Exponential backoff retry policy."""

    max_retries: int = 3
    base_delay_seconds: int = 5  # first retry delay
    max_delay_seconds: int = 300  # cap at 5 minutes
    backoff_multiplier: float = 2.0

    def delay_for_attempt(self, attempt: int) -> int:
        """Calculate delay in seconds for the given retry attempt (0-indexed)."""
        delay = self.base_delay_seconds * (self.backoff_multiplier ** attempt)
        return min(int(delay), self.max_delay_seconds)


DEFAULT_RETRY_POLICY = RetryPolicy()


# ---------------------------------------------------------------------------
# Job Runner
# ---------------------------------------------------------------------------

@dataclass
class JobResult:
    """Result of a job execution attempt."""

    success: bool
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


JobHandler = Callable[..., JobResult]


class JobRunner:
    """
    Manages background job execution with retry logic.

    Usage:
        runner = JobRunner()

        def my_handler(payload):
            # do work...
            return JobResult(success=True)

        runner.register_handler("send_reminder", my_handler)

        # Create and run jobs
        job = runner.enqueue("send_reminder", payload={"reminder_id": 1})
        runner.process_due_jobs()
    """

    def __init__(self, retry_policy: RetryPolicy | None = None):
        self.retry_policy = retry_policy or DEFAULT_RETRY_POLICY
        self._handlers: dict[str, JobHandler] = {}

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler function for a job type."""
        self._handlers[job_type] = handler

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        max_retries: int | None = None,
        scheduled_at: datetime | None = None,
    ) -> BackgroundJob:
        """
        Create a new background job in PENDING status.

        Args:
            job_type: The type identifier for this job (must have a registered handler).
            payload: JSON-serializable data for the handler.
            max_retries: Override the default retry policy max_retries.
            scheduled_at: When to run the job (defaults to now).

        Returns:
            The created BackgroundJob instance.
        """
        job = BackgroundJob(
            job_type=job_type,
            payload=payload,
            status=JobStatus.PENDING.value,
            max_retries=max_retries if max_retries is not None else self.retry_policy.max_retries,
            scheduled_at=scheduled_at or datetime.utcnow(),
        )
        db.session.add(job)
        db.session.flush()  # get the ID
        logger.info("Enqueued job id=%s type=%s", job.id, job_type)
        return job

    def process_due_jobs(self, *, job_type: str | None = None) -> int:
        """
        Process all jobs that are due (PENDING or RETRYING with scheduled_at <= now).

        Args:
            job_type: Optional filter to process only this job type.

        Returns:
            Number of jobs processed.
        """
        now = datetime.utcnow()
        query = BackgroundJob.query.filter(
            BackgroundJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRYING.value]),
            BackgroundJob.scheduled_at <= now,
        )
        if job_type:
            query = query.filter_by(job_type=job_type)

        jobs = query.order_by(BackgroundJob.scheduled_at).all()
        processed = 0

        for job in jobs:
            self._execute_job(job)
            processed += 1

        if processed:
            db.session.commit()
            logger.info("Processed %d due jobs", processed)

        return processed

    def _execute_job(self, job: BackgroundJob) -> None:
        """Execute a single job with retry logic."""
        handler = self._handlers.get(job.job_type)
        if not handler:
            job.status = JobStatus.FAILED.value
            job.error_message = f"No handler registered for job type: {job.job_type}"
            job.completed_at = datetime.utcnow()
            logger.error("Job id=%s failed: no handler for type=%s", job.id, job.job_type)
            return

        job.status = JobStatus.RUNNING.value
        job.attempts += 1
        job.last_attempt_at = datetime.utcnow()

        try:
            payload = job.payload or {}
            result = handler(**payload)

            if result.success:
                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.utcnow()
                if result.metadata:
                    job.result_metadata = result.metadata
                logger.info(
                    "Job id=%s type=%s completed on attempt %d",
                    job.id, job.job_type, job.attempts,
                )
            else:
                self._handle_failure(job, result.error_message or "Unknown error")

        except Exception as exc:
            logger.exception("Job id=%s type=%s raised exception", job.id, job.job_type)
            self._handle_failure(job, str(exc))

    def _handle_failure(self, job: BackgroundJob, error_message: str) -> None:
        """Handle a failed job attempt — retry or dead-letter."""
        job.error_message = error_message

        if job.attempts >= job.max_retries:
            job.status = JobStatus.DEAD.value
            job.completed_at = datetime.utcnow()
            logger.warning(
                "Job id=%s type=%s moved to DEAD after %d attempts. Error: %s",
                job.id, job.job_type, job.attempts, error_message,
            )
        else:
            job.status = JobStatus.RETRYING.value
            delay = self.retry_policy.delay_for_attempt(job.attempts - 1)
            job.scheduled_at = datetime.utcnow() + timedelta(seconds=delay)
            job.next_retry_at = job.scheduled_at
            logger.info(
                "Job id=%s type=%s attempt %d failed, retrying in %ds. Error: %s",
                job.id, job.job_type, job.attempts, delay, error_message,
            )

    # -----------------------------------------------------------------------
    # Monitoring / introspection
    # -----------------------------------------------------------------------

    @staticmethod
    def get_stats() -> dict[str, Any]:
        """Get aggregated job statistics."""
        from sqlalchemy import func

        rows = (
            db.session.query(
                BackgroundJob.status,
                func.count(BackgroundJob.id),
            )
            .group_by(BackgroundJob.status)
            .all()
        )
        stats = {status: 0 for status in JobStatus}
        for status, count in rows:
            stats[status] = count

        # Recent failures (last 24h)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_failures = BackgroundJob.query.filter(
            BackgroundJob.status == JobStatus.DEAD.value,
            BackgroundJob.completed_at >= cutoff,
        ).count()

        return {
            "by_status": stats,
            "total": sum(stats.values()),
            "dead_last_24h": recent_failures,
        }

    @staticmethod
    def get_dead_jobs(limit: int = 50) -> list[dict[str, Any]]:
        """Get dead-lettered jobs for manual inspection."""
        jobs = (
            BackgroundJob.query.filter_by(status=JobStatus.DEAD.value)
            .order_by(BackgroundJob.completed_at.desc())
            .limit(limit)
            .all()
        )
        return [_serialize_job(j) for j in jobs]

    @staticmethod
    def get_retrying_jobs(limit: int = 50) -> list[dict[str, Any]]:
        """Get jobs currently waiting for retry."""
        jobs = (
            BackgroundJob.query.filter_by(status=JobStatus.RETRYING.value)
            .order_by(BackgroundJob.scheduled_at)
            .limit(limit)
            .all()
        )
        return [_serialize_job(j) for j in jobs]

    @staticmethod
    def retry_dead_job(job_id: int) -> bool:
        """Manually retry a dead-lettered job by resetting it to PENDING."""
        job = db.session.get(BackgroundJob, job_id)
        if not job or job.status != JobStatus.DEAD.value:
            return False
        job.status = JobStatus.PENDING.value
        job.scheduled_at = datetime.utcnow()
        job.next_retry_at = None
        db.session.commit()
        logger.info("Dead job id=%s reset to PENDING for manual retry", job_id)
        return True


def _serialize_job(job: BackgroundJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "attempts": job.attempts,
        "max_retries": job.max_retries,
        "error_message": job.error_message,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "last_attempt_at": job.last_attempt_at.isoformat() if job.last_attempt_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "payload": job.payload,
    }
