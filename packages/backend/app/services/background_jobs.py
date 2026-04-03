"""
Background Job Queue Architecture (issue #71)

Async processing for heavy operations: imports, AI analysis, reminders.
Uses a database-backed job queue with retry logic and status tracking.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from sqlalchemy import func
from app.extensions import db


# Job status lifecycle: PENDING -> RUNNING -> COMPLETED | FAILED | CANCELLED
class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


PRIORITY_ORDER = {
    JobPriority.CRITICAL: 0,
    JobPriority.HIGH: 1,
    JobPriority.NORMAL: 2,
    JobPriority.LOW: 3,
}

# Registry of job handlers by job_type
_JOB_HANDLERS: dict[str, Callable] = {}

MAX_RETRIES_DEFAULT = 3
RETRY_BACKOFF_SECONDS = [60, 300, 900]  # 1m, 5m, 15m


class BackgroundJob(db.Model):
    """Persistent job record for async background processing."""

    __tablename__ = "background_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    job_type = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default=JobStatus.PENDING.value, nullable=False)
    priority = db.Column(db.String(20), default=JobPriority.NORMAL.value, nullable=False)
    payload = db.Column(db.Text, nullable=False, default="{}")
    result = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    max_retries = db.Column(db.Integer, default=MAX_RETRIES_DEFAULT, nullable=False)
    scheduled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def get_payload(self) -> dict:
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_payload(self, data: dict) -> None:
        self.payload = json.dumps(data)

    def get_result(self) -> Optional[dict]:
        if self.result:
            try:
                return json.loads(self.result)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "job_type": self.job_type,
            "status": self.status,
            "priority": self.priority,
            "payload": self.get_payload(),
            "result": self.get_result(),
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def register_job_handler(job_type: str):
    """Decorator to register a function as a job handler."""
    def decorator(fn: Callable) -> Callable:
        _JOB_HANDLERS[job_type] = fn
        return fn
    return decorator


def get_registered_job_types() -> list[str]:
    return list(_JOB_HANDLERS.keys())


def enqueue_job(
    job_type: str,
    payload: dict,
    user_id: Optional[int] = None,
    priority: str = JobPriority.NORMAL.value,
    max_retries: int = MAX_RETRIES_DEFAULT,
    scheduled_at: Optional[datetime] = None,
) -> BackgroundJob:
    """Create and enqueue a new background job."""
    job = BackgroundJob(
        user_id=user_id,
        job_type=job_type,
        status=JobStatus.PENDING.value,
        priority=priority,
        max_retries=max_retries,
        scheduled_at=scheduled_at or datetime.utcnow(),
    )
    job.set_payload(payload)
    db.session.add(job)
    db.session.commit()
    return job


def get_next_pending_job() -> Optional[BackgroundJob]:
    """Get the highest-priority pending job that is ready to run."""
    now = datetime.utcnow()
    # Priority order: critical=0, high=1, normal=2, low=3
    priority_case = db.case(
        {
            JobPriority.CRITICAL.value: 0,
            JobPriority.HIGH.value: 1,
            JobPriority.NORMAL.value: 2,
            JobPriority.LOW.value: 3,
        },
        value=BackgroundJob.priority,
        else_=99,
    )
    return (
        BackgroundJob.query.filter(
            BackgroundJob.status == JobStatus.PENDING.value,
            BackgroundJob.scheduled_at <= now,
        )
        .order_by(priority_case, BackgroundJob.scheduled_at)
        .first()
    )


def process_job(job: BackgroundJob) -> bool:
    """
    Execute a single job. Returns True on success, False on failure.
    Handles retry scheduling and status transitions.
    """
    handler = _JOB_HANDLERS.get(job.job_type)
    if not handler:
        job.status = JobStatus.FAILED.value
        job.error_message = f"No handler registered for job_type: {job.job_type}"
        job.completed_at = datetime.utcnow()
        db.session.commit()
        return False

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        result = handler(job.get_payload(), user_id=job.user_id)
        job.status = JobStatus.COMPLETED.value
        job.result = json.dumps(result) if result is not None else json.dumps({})
        job.completed_at = datetime.utcnow()
        db.session.commit()
        return True
    except Exception as exc:
        job.retry_count += 1
        job.error_message = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()[-500:]}"

        if job.retry_count <= job.max_retries:
            backoff_idx = min(job.retry_count - 1, len(RETRY_BACKOFF_SECONDS) - 1)
            delay_seconds = RETRY_BACKOFF_SECONDS[backoff_idx]
            job.status = JobStatus.PENDING.value
            job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
            job.scheduled_at = job.next_retry_at
        else:
            job.status = JobStatus.FAILED.value
            job.completed_at = datetime.utcnow()

        db.session.commit()
        return False


def cancel_job(job_id: int, user_id: Optional[int] = None) -> Optional[BackgroundJob]:
    """Cancel a pending job. Returns job if cancelled, None if not found or not cancellable."""
    query = BackgroundJob.query.filter_by(id=job_id)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    job = query.first()
    if not job:
        return None
    if job.status not in (JobStatus.PENDING.value, JobStatus.FAILED.value):
        return None  # Can only cancel pending/failed jobs
    job.status = JobStatus.CANCELLED.value
    job.completed_at = datetime.utcnow()
    db.session.commit()
    return job


def get_job_stats(user_id: Optional[int] = None) -> dict:
    """Get job statistics, optionally scoped to a user."""
    query = BackgroundJob.query
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    stats = {}
    for status in JobStatus:
        count = query.filter_by(status=status.value).count()
        stats[status.value] = count

    stats["total"] = query.count()
    stats["registered_job_types"] = get_registered_job_types()
    return stats


def get_user_jobs(
    user_id: int,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Get jobs for a user with optional filters."""
    query = BackgroundJob.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    if job_type:
        query = query.filter_by(job_type=job_type)

    total = query.count()
    jobs = query.order_by(BackgroundJob.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "jobs": [j.to_dict() for j in jobs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# -----------------------------------------------------------------------
# Built-in job handlers for common FinMind operations
# -----------------------------------------------------------------------

@register_job_handler("expense_import")
def handle_expense_import(payload: dict, user_id: Optional[int] = None) -> dict:
    """Process bulk expense import from CSV/bank statement."""
    rows = payload.get("rows", [])
    processed = 0
    skipped = 0
    errors = []

    for row in rows:
        try:
            # Validate minimum fields
            if not row.get("amount") or not row.get("date"):
                skipped += 1
                continue
            # In real impl: create Expense records
            processed += 1
        except Exception as e:
            errors.append(str(e))
            skipped += 1

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors[:10],  # cap error list
        "total": len(rows),
    }


@register_job_handler("ai_spending_analysis")
def handle_ai_analysis(payload: dict, user_id: Optional[int] = None) -> dict:
    """Run AI-powered spending analysis for a user."""
    period = payload.get("period", "last_30_days")
    # In real impl: call AI service, generate insights
    return {
        "analysis_id": f"ai_{user_id}_{period}",
        "status": "completed",
        "insights_generated": 0,
    }


@register_job_handler("reminder_dispatch")
def handle_reminder_dispatch(payload: dict, user_id: Optional[int] = None) -> dict:
    """Send due reminders for bills and recurring expenses."""
    reminder_ids = payload.get("reminder_ids", [])
    sent = 0
    failed = 0
    for rid in reminder_ids:
        # In real impl: send email/push notification
        sent += 1
    return {"sent": sent, "failed": failed, "total": len(reminder_ids)}


@register_job_handler("statement_normalization")
def handle_statement_normalization(payload: dict, user_id: Optional[int] = None) -> dict:
    """Normalize a bank statement in the background."""
    content = payload.get("content", "")
    file_format = payload.get("format", "auto")
    # In real impl: call normalize_statement()
    return {
        "rows_parsed": 0,
        "format_detected": file_format,
        "status": "completed",
    }