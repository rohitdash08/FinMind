"""
Resilient background job execution with retry, dead-letter queue, and monitoring.

Implements:
- RetryPolicy with configurable exponential backoff (5min → 15min → 45min, max 3 attempts)
- Dead-letter queue for permanently failed jobs
- Monitoring functions for job statistics
- Pure dispatch/marking functions for testability
- Scheduler integration that processes pending/retrying jobs

Models (JobStatus, JobType, JobExecution) live in models.py.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, func

from ..extensions import db
from ..models import JobExecution, JobStatus, JobType, Reminder
from ..services.reminders import send_reminder

logger = logging.getLogger("finmind.jobs")


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------

class RetryPolicy:
    """
    Configurable exponential backoff retry policy.

    Default schedule: 5min → 15min → 45min (3 attempts total).
    All intervals are configurable via environment variables.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: timedelta = timedelta(minutes=5),
        max_delay: timedelta = timedelta(minutes=60),
        backoff_factor: float = 3.0,
    ):
        self.max_attempts = max(1, max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def next_retry_at(self, attempt: int) -> Optional[datetime]:
        """Calculate the next retry timestamp for a given attempt number (0-indexed)."""
        if attempt >= self.max_attempts:
            return None
        delay = self.base_delay * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay)
        return datetime.utcnow() + delay

    def should_retry(self, attempt: int) -> bool:
        """Return True if the job can be retried based on attempt count."""
        return attempt < self.max_attempts

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        """Create a RetryPolicy from environment variables with sensible defaults."""
        import os
        return cls(
            max_attempts=int(os.getenv("JOB_RETRY_MAX_ATTEMPTS", "3")),
            base_delay=timedelta(minutes=int(os.getenv("JOB_RETRY_BASE_DELAY_MIN", "5"))),
            max_delay=timedelta(minutes=int(os.getenv("JOB_RETRY_MAX_DELAY_MIN", "60"))),
            backoff_factor=float(os.getenv("JOB_RETRY_BACKOFF_FACTOR", "3.0")),
        )


# Module-level default policy (overridable in tests)
_default_policy: Optional[RetryPolicy] = None


def get_retry_policy() -> RetryPolicy:
    """Get the default retry policy, initializing from env if needed."""
    global _default_policy
    if _default_policy is None:
        _default_policy = RetryPolicy.from_env()
    return _default_policy


def set_retry_policy(policy: RetryPolicy) -> None:
    """Override the default retry policy (useful in tests)."""
    global _default_policy
    _default_policy = policy


# ---------------------------------------------------------------------------
# Job lifecycle helpers (pure DB operations)
# ---------------------------------------------------------------------------

def dispatch_job(
    job_type: JobType,
    payload: str,
    *,
    source_id: Optional[int] = None,
    source_type: Optional[str] = None,
    max_attempts: int = 3,
    policy: Optional[RetryPolicy] = None,
) -> JobExecution:
    """
    Create a new job execution record and enqueue it for processing.

    This is a pure function that only creates the DB record; the actual
    execution is handled by the scheduler's tick loop.

    Args:
        job_type: Category of the job.
        payload: JSON-serialized job data.
        source_id: Optional foreign key to the originating entity.
        source_type: Type of the originating entity (e.g. "reminder").
        max_attempts: Maximum retry attempts before dead-lettering.
        policy: Retry policy to apply. Uses default if None.

    Returns:
        The created JobExecution record.
    """
    policy = policy or get_retry_policy()
    max_attempts = min(max_attempts, policy.max_attempts) if policy else max_attempts

    job = JobExecution(
        job_type=job_type,
        payload=payload,
        source_id=source_id,
        source_type=source_type,
        status=JobStatus.PENDING,
        attempt=0,
        max_attempts=max_attempts,
    )
    db.session.add(job)
    db.session.commit()
    return job


def mark_running(job: JobExecution) -> JobExecution:
    """Mark a job as currently running."""
    job.status = JobStatus.RUNNING
    job.started_at = job.started_at or datetime.utcnow()
    db.session.commit()
    return job


def mark_success(job: JobExecution, result: Optional[str] = None) -> JobExecution:
    """Mark a job as successfully completed."""
    job.status = JobStatus.SUCCESS
    job.completed_at = datetime.utcnow()
    if result is not None:
        job.result = result
    db.session.commit()
    return job


def mark_failed(job: JobExecution, error: str, policy: Optional[RetryPolicy] = None) -> JobExecution:
    """
    Mark a job as failed. If retries remain, schedule the next attempt.
    Otherwise, move to the dead-letter queue.
    """
    policy = policy or get_retry_policy()

    job.attempt += 1
    job.result = error

    if policy.should_retry(job.attempt):
        job.status = JobStatus.RETRYING
        job.next_retry_at = policy.next_retry_at(job.attempt - 1)
    else:
        # Max retries exceeded → dead-letter
        job.status = JobStatus.DEAD
        job.dead_reason = error
        job.dead_at = datetime.utcnow()
        job.next_retry_at = None

    db.session.commit()
    return job


def retry_dead_letter(job_id: int, policy: Optional[RetryPolicy] = None) -> Optional[JobExecution]:
    """
    Manually retry a dead-lettered job, resetting its status to PENDING.

    Returns the updated job, or None if not found or not in DEAD state.
    """
    job = db.session.get(JobExecution, job_id)
    if not job or job.status != JobStatus.DEAD:
        return None

    policy = policy or get_retry_policy()
    job.status = JobStatus.PENDING
    job.attempt = 0
    job.dead_reason = None
    job.dead_at = None
    job.next_retry_at = None
    job.result = None
    job.started_at = None
    job.completed_at = None
    job.max_attempts = policy.max_attempts
    db.session.commit()
    return job


# ---------------------------------------------------------------------------
# Job execution logic
# ---------------------------------------------------------------------------

def execute_reminder_job(job: JobExecution) -> bool:
    """
    Execute a REMINDER job by looking up the Reminder and sending it.

    Returns True if the reminder was sent successfully, False otherwise.
    """
    try:
        data = json.loads(job.payload)
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat payload as a reminder_id
        try:
            reminder_id = int(job.payload)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid payload for REMINDER job {job.id}")

        reminder = db.session.get(Reminder, reminder_id)
        if not reminder:
            raise ValueError(f"Reminder {reminder_id} not found")
        success = send_reminder(reminder)
        if success:
            reminder.sent = True
            db.session.commit()
        return success

    # Payload contains reminder details
    reminder_id = data.get("reminder_id")
    if reminder_id:
        reminder = db.session.get(Reminder, reminder_id)
        if not reminder:
            raise ValueError(f"Reminder {reminder_id} not found")
        success = send_reminder(reminder)
        if success:
            reminder.sent = True
            db.session.commit()
        return success

    # No reminder_id in payload — we can't execute without one
    raise ValueError(f"No reminder_id in payload for job {job.id}")


def execute_job(job: JobExecution) -> JobExecution:
    """
    Execute a single job with proper lifecycle management.

    Marks the job RUNNING, attempts execution, then marks SUCCESS or
    schedules a retry / dead-letters on failure.
    """
    mark_running(job)

    try:
        if job.job_type == JobType.REMINDER:
            success = execute_reminder_job(job)
            if success:
                return mark_success(job, result="sent")
            else:
                return mark_failed(job, error="send returned False")
        else:
            # Generic job types — for now, just mark success
            # Future: add handlers for EMAIL, WHATSAPP, IMPORT, INSIGHT
            return mark_success(job, result="completed")

    except Exception as exc:
        logger.exception("Job %s execution failed", job.id)
        return mark_failed(job, error=str(exc))


# ---------------------------------------------------------------------------
# Scheduler tick — processes due jobs
# ---------------------------------------------------------------------------

def tick() -> dict:
    """
    Process all due jobs: PENDING jobs and RETRYING jobs past their next_retry_at.

    Returns a summary of processed jobs.
    """
    now = datetime.utcnow()

    # Find PENDING jobs
    pending = (
        db.session.query(JobExecution)
        .filter_by(status=JobStatus.PENDING)
        .all()
    )

    # Find RETRYING jobs that are due
    retrying = (
        db.session.query(JobExecution)
        .filter(
            JobExecution.status == JobStatus.RETRYING,
            JobExecution.next_retry_at <= now,
        )
        .all()
    )

    due_jobs = list(pending) + list(retrying)
    results = {"processed": 0, "success": 0, "failed": 0}

    for job in due_jobs:
        try:
            job = execute_job(job)
            results["processed"] += 1
            if job.status == JobStatus.SUCCESS:
                results["success"] += 1
            else:
                results["failed"] += 1
        except Exception:
            logger.exception("Unexpected error processing job %s", job.id)
            results["processed"] += 1
            results["failed"] += 1

    return results


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

def get_job_stats() -> dict:
    """Return aggregate statistics for all job executions."""
    total = db.session.query(func.count(JobExecution.id)).scalar() or 0
    by_status = dict(
        db.session.query(JobExecution.status, func.count(JobExecution.id))
        .group_by(JobExecution.status)
        .all()
    )
    by_type = dict(
        db.session.query(JobExecution.job_type, func.count(JobExecution.id))
        .group_by(JobExecution.job_type)
        .all()
    )

    # Success rate
    success_count = by_status.get(JobStatus.SUCCESS, 0)
    dead_count = by_status.get(JobStatus.DEAD, 0)
    finished = success_count + dead_count
    success_rate = round(success_count / finished * 100, 1) if finished > 0 else 0.0

    # Average duration for completed jobs
    avg_duration = (
        db.session.query(
            func.avg(
                func.extract("epoch", JobExecution.completed_at - JobExecution.started_at)
            )
        )
        .filter(
            JobExecution.started_at.isnot(None),
            JobExecution.completed_at.isnot(None),
        )
        .scalar()
    )

    # Recent dead-lettered jobs (last 10)
    recent_dead = (
        db.session.query(JobExecution)
        .filter_by(status=JobStatus.DEAD)
        .order_by(desc(JobExecution.dead_at))
        .limit(10)
        .all()
    )

    return {
        "total": total,
        "by_status": {k.value if hasattr(k, "value") else str(k): v for k, v in by_status.items()},
        "by_type": {k.value if hasattr(k, "value") else str(k): v for k, v in by_type.items()},
        "success_rate": success_rate,
        "avg_duration_seconds": round(avg_duration, 2) if avg_duration else None,
        "recent_dead": [j.to_dict() for j in recent_dead],
    }