from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ..extensions import db
from ..models import BackgroundJob, BackgroundJobStatus, Reminder
from .reminders import send_reminder


class UnknownJobError(ValueError):
    pass


def enqueue_job(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    user_id: int | None = None,
    run_at: datetime | None = None,
    max_attempts: int = 3,
) -> BackgroundJob:
    """Persist a durable background job for later execution."""
    job = BackgroundJob(
        user_id=user_id,
        name=name,
        payload=payload or {},
        run_at=run_at or datetime.utcnow(),
        max_attempts=max(1, min(int(max_attempts), 10)),
        status=BackgroundJobStatus.QUEUED.value,
    )
    db.session.add(job)
    db.session.commit()
    return job


def run_due_jobs(*, limit: int = 25, now: datetime | None = None) -> dict[str, int]:
    """Run due jobs once, applying bounded exponential retry on failure."""
    now = now or datetime.utcnow()
    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.status.in_(
                [BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RETRYING.value]
            ),
            BackgroundJob.run_at <= now,
        )
        .order_by(BackgroundJob.run_at.asc(), BackgroundJob.id.asc())
        .limit(limit)
        .all()
    )
    stats = {"processed": 0, "succeeded": 0, "retrying": 0, "failed": 0}
    for job in jobs:
        stats["processed"] += 1
        _run_one(job, now)
        if job.status == BackgroundJobStatus.SUCCEEDED.value:
            stats["succeeded"] += 1
        elif job.status == BackgroundJobStatus.RETRYING.value:
            stats["retrying"] += 1
        elif job.status == BackgroundJobStatus.FAILED.value:
            stats["failed"] += 1
    db.session.commit()
    return stats


def _run_one(job: BackgroundJob, now: datetime) -> None:
    job.status = BackgroundJobStatus.RUNNING.value
    job.locked_at = now
    job.attempts += 1
    job.updated_at = now
    db.session.flush()
    try:
        _execute(job)
    except Exception as exc:  # pragma: no cover - exact exception varies by job
        current_app.logger.warning(
            "background job failed id=%s name=%s attempt=%s/%s",
            job.id,
            job.name,
            job.attempts,
            job.max_attempts,
            exc_info=True,
        )
        job.last_error = str(exc)[:1000]
        if job.attempts >= job.max_attempts:
            job.status = BackgroundJobStatus.FAILED.value
        else:
            job.status = BackgroundJobStatus.RETRYING.value
            delay_seconds = min(3600, 2 ** (job.attempts - 1) * 60)
            job.run_at = now + timedelta(seconds=delay_seconds)
    else:
        job.status = BackgroundJobStatus.SUCCEEDED.value
        job.last_error = None
    finally:
        job.locked_at = None
        job.updated_at = datetime.utcnow()


def _execute(job: BackgroundJob) -> None:
    if job.name == "noop":
        return
    if job.name == "fail":
        raise RuntimeError(str(job.payload.get("message") or "intentional failure"))
    if job.name == "send_reminder":
        reminder_id = job.payload.get("reminder_id")
        reminder = db.session.get(Reminder, reminder_id)
        if reminder is None:
            raise ValueError(f"reminder {reminder_id} not found")
        ok = send_reminder(reminder)
        if not ok:
            raise RuntimeError("reminder delivery failed")
        reminder.sent = True
        return
    raise UnknownJobError(f"unknown job name: {job.name}")


def serialize_job(job: BackgroundJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "name": job.name,
        "payload": job.payload,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "run_at": job.run_at.isoformat(),
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
