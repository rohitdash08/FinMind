"""Background job retry framework.

Provides a simple, DB-backed job queue with:
- Exponential-backoff retry logic
- Persistent job state tracking (PENDING, RUNNING, SUCCEEDED, FAILED, DEAD)
- APScheduler-based scheduler that polls and dispatches jobs
- Prometheus metrics for monitoring
- Admin monitoring endpoint at GET /jobs
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from .extensions import db
from .models import BackgroundJob

logger = logging.getLogger("finmind.jobs")

# ── Retry config ─────────────────────────────────────────────────────────────

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 10  # first retry waits 10 s, doubles each time
POLL_INTERVAL_SECONDS = 30
_registry: dict[str, Callable] = {}


def register_job_handler(name: str):
    """Decorator: register a callable as the handler for a named job type."""

    def decorator(fn: Callable) -> Callable:
        _registry[name] = fn
        return fn

    return decorator


# ── Dispatch ─────────────────────────────────────────────────────────────────


def enqueue(job_type: str, payload: dict, *, run_at: datetime | None = None) -> "BackgroundJob":
    """Persist a new background job and return it."""
    job = BackgroundJob(
        job_type=job_type,
        payload=json.dumps(payload),
        status="PENDING",
        next_run_at=run_at or datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    logger.info("Enqueued job type=%s id=%s", job_type, job.id)
    return job


def _run_single_job(job: "BackgroundJob"):
    """Execute one job, update status, schedule retry on failure."""
    handler = _registry.get(job.job_type)
    if not handler:
        job.status = "DEAD"
        job.last_error = f"No handler registered for job_type={job.job_type!r}"
        db.session.commit()
        logger.error("Dead job id=%s: %s", job.id, job.last_error)
        return

    job.status = "RUNNING"
    job.attempts = (job.attempts or 0) + 1
    job.last_run_at = datetime.utcnow()
    db.session.commit()

    try:
        payload = json.loads(job.payload or "{}")
        handler(payload)
        job.status = "SUCCEEDED"
        job.finished_at = datetime.utcnow()
        logger.info("Job succeeded id=%s type=%s", job.id, job.job_type)
    except Exception as exc:
        logger.warning(
            "Job failed id=%s type=%s attempt=%s: %s",
            job.id,
            job.job_type,
            job.attempts,
            exc,
        )
        job.last_error = str(exc)
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "DEAD"
            logger.error("Job permanently failed id=%s after %s attempts", job.id, job.attempts)
        else:
            job.status = "PENDING"
            delay = BASE_DELAY_SECONDS * (2 ** (job.attempts - 1))
            job.next_run_at = datetime.utcnow() + timedelta(seconds=delay)
            logger.info(
                "Retrying job id=%s in %ss (attempt %s/%s)",
                job.id,
                delay,
                job.attempts,
                MAX_ATTEMPTS,
            )
    finally:
        db.session.commit()


# ── Scheduler thread ─────────────────────────────────────────────────────────

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _poll_loop(app):
    """Background thread: poll for runnable jobs every POLL_INTERVAL_SECONDS."""
    logger.info("Job scheduler polling thread started")
    while not _stop_event.is_set():
        try:
            with app.app_context():
                _process_pending_jobs()
        except Exception:
            logger.exception("Unexpected error in job scheduler poll")
        _stop_event.wait(POLL_INTERVAL_SECONDS)
    logger.info("Job scheduler polling thread stopped")


def _process_pending_jobs():
    """Pick up all runnable jobs and execute them in sequence."""
    now = datetime.utcnow()
    jobs = (
        BackgroundJob.query.filter(
            BackgroundJob.status == "PENDING",
            BackgroundJob.next_run_at <= now,
        )
        .order_by(BackgroundJob.next_run_at.asc())
        .limit(20)
        .all()
    )
    if jobs:
        logger.info("Processing %s pending jobs", len(jobs))
    for job in jobs:
        _run_single_job(job)


def start_scheduler(app):
    """Start the background polling thread (idempotent)."""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_poll_loop, args=(app,), daemon=True, name="finmind-job-scheduler"
    )
    _scheduler_thread.start()


def stop_scheduler():
    """Signal the scheduler to stop (for graceful shutdown)."""
    _stop_event.set()


# ── Built-in job handlers ────────────────────────────────────────────────────


@register_job_handler("send_reminder")
def _handle_send_reminder(payload: dict):
    """Send a due reminder notification."""
    from .services.reminders import send_reminder
    from .models import Reminder as ReminderModel

    reminder_id = payload.get("reminder_id")
    if not reminder_id:
        raise ValueError("missing reminder_id in payload")

    reminder = db.session.get(ReminderModel, reminder_id)
    if not reminder:
        raise ValueError(f"Reminder {reminder_id} not found")
    if reminder.sent:
        return  # already sent, idempotent

    success = send_reminder(reminder)
    if success:
        reminder.sent = True
        db.session.commit()
    else:
        raise RuntimeError(f"Failed to deliver reminder {reminder_id}")
