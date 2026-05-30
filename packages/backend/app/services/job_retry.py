"""Resilient background job retry & monitoring (issue #130).

Provides:
- JobRecord        — per-job execution state snapshot
- JobMonitor       — in-process registry of all scheduled job records
- retryable()      — decorator factory: wraps a job fn with exponential-backoff retry
                     and automatic JobMonitor recording
- init_job_scheduler(app) — registers the reminder-dispatch job on APScheduler
                            (every minute) and exposes the scheduler on app.extensions

Public API
----------
job_monitor          : JobMonitor           — singleton, importable anywhere
retryable(name, ...)                        — decorator
init_job_scheduler(app) -> BackgroundScheduler
"""
from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger("finmind.job_retry")


# ---------------------------------------------------------------------------
# JobRecord + JobMonitor
# ---------------------------------------------------------------------------

@dataclass
class JobRecord:
    name: str
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_run: datetime | None = None
    last_success: datetime | None = None
    last_failure: datetime | None = None
    last_error: str | None = None
    status: str = "idle"   # idle | running | success | failed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_error": self.last_error,
        }


class JobMonitor:
    """Thread-safe, in-process job registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def register(self, name: str) -> JobRecord:
        with self._lock:
            if name not in self._jobs:
                self._jobs[name] = JobRecord(name=name)
            return self._jobs[name]

    def get_record(self, name: str) -> JobRecord | None:
        return self._jobs.get(name)

    def all_records(self) -> list[JobRecord]:
        return list(self._jobs.values())

    def to_dict(self) -> dict:
        return {name: rec.to_dict() for name, rec in self._jobs.items()}

    def reset(self) -> None:
        """For test isolation only."""
        with self._lock:
            self._jobs.clear()


# Module-level singleton — all code shares one monitor instance.
job_monitor: JobMonitor = JobMonitor()


# ---------------------------------------------------------------------------
# retryable decorator
# ---------------------------------------------------------------------------

def retryable(
    name: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    app: Any = None,
) -> Callable:
    """Return a decorator that wraps *fn* with retry logic and job monitoring.

    Parameters
    ----------
    name        : human-readable job name recorded in the monitor
    max_retries : how many extra attempts after the first failure (default 3)
    backoff_base: base for exponential back-off in seconds (default 2.0)
                  delay = backoff_base ** attempt  (0s, 2s, 4s, 8s, …)
    app         : Flask app to push an app-context on each attempt (optional)
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            record = job_monitor.register(name)
            with job_monitor._lock:
                record.run_count += 1
                record.last_run = datetime.utcnow()
                record.status = "running"

            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                if attempt > 0:
                    sleep_secs = backoff_base ** (attempt - 1)
                    logger.warning(
                        "Job %s retry %d/%d after %.1fs back-off",
                        name, attempt, max_retries, sleep_secs,
                    )
                    time.sleep(sleep_secs)
                try:
                    if app is not None:
                        with app.app_context():
                            result = fn(*args, **kwargs)
                    else:
                        result = fn(*args, **kwargs)

                    with job_monitor._lock:
                        record.last_success = datetime.utcnow()
                        record.success_count += 1
                        record.status = "success"
                        record.last_error = None
                    logger.debug("Job %s succeeded (attempt %d)", name, attempt + 1)
                    return result

                except Exception as exc:
                    last_exc = exc
                    logger.error(
                        "Job %s attempt %d/%d failed: %s",
                        name, attempt + 1, max_retries + 1, exc,
                    )

            # All attempts exhausted
            with job_monitor._lock:
                record.last_failure = datetime.utcnow()
                record.failure_count += 1
                record.status = "failed"
                record.last_error = str(last_exc)
            logger.error(
                "Job %s permanently failed after %d attempt(s): %s",
                name, max_retries + 1, last_exc,
            )

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Reminder-dispatch job (runs every minute)
# ---------------------------------------------------------------------------

def _dispatch_due_reminders_job(app) -> dict:
    """Dispatch all due, unsent reminders.  Returns stats dict."""
    from datetime import timedelta
    from ..extensions import db
    from ..models import Reminder
    from .reminders import send_reminder

    now = datetime.utcnow() + timedelta(minutes=1)
    items = (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.send_at <= now,
        )
        .all()
    )
    sent = failed = 0
    for r in items:
        try:
            send_reminder(r)
            r.sent = True
            sent += 1
        except Exception as exc:
            logger.warning("Failed to send reminder id=%s: %s", r.id, exc)
            failed += 1
    db.session.commit()
    logger.info("Reminder dispatch: sent=%s failed=%s", sent, failed)
    return {"sent": sent, "failed": failed}


def init_job_scheduler(app):
    """Register all background jobs on a BackgroundScheduler and start it.

    The scheduler is stored at ``app.extensions['job_scheduler']`` so callers
    can inspect or shut it down.

    Skipped automatically when ``TESTING=true`` or ``DISABLE_SCHEDULER`` is set
    (checked externally in create_app — this function unconditionally starts the
    scheduler when called, caller is responsible for the guard).
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()

    # Wrap the reminder dispatch job with retry logic
    monitored_dispatch = retryable(
        "reminder_dispatch",
        max_retries=3,
        backoff_base=2.0,
        app=app,
    )(_dispatch_due_reminders_job)

    scheduler.add_job(
        monitored_dispatch,
        trigger="interval",
        minutes=1,
        id="reminder_dispatch",
        replace_existing=True,
        args=[app],
    )

    scheduler.start()
    app.extensions["job_scheduler"] = scheduler
    logger.info("Job scheduler started with %d job(s)", len(scheduler.get_jobs()))
    return scheduler
