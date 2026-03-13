"""Resilient background job manager with retry and monitoring.

Wraps APScheduler to provide:
- Automatic retry with configurable exponential backoff
- Dead-letter tracking for permanently failed jobs
- Per-job execution history with timing and error details
- Prometheus metrics integration
- Redis-backed state persistence for crash recovery
- Health check endpoint data
"""

import functools
import json
import logging
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
)
from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger("finmind.jobs")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    RETRYING = "retrying"
    FAILED = "failed"         # exhausted retries → dead-letter
    MISSED = "missed"


@dataclass
class RetryPolicy:
    """Configurable retry behaviour for a job."""
    max_retries: int = 3
    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0
    backoff_factor: float = 2.0

    def delay_for_attempt(self, attempt: int) -> float:
        delay = self.base_delay_seconds * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay_seconds)


@dataclass
class JobExecution:
    """Single execution record for audit / monitoring."""
    job_id: str
    attempt: int
    status: str
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    error: str | None = None


@dataclass
class JobState:
    """Persistent state for a managed job."""
    job_id: str
    attempt: int = 0
    last_status: str = JobStatus.PENDING.value
    last_error: str | None = None
    last_run_at: str | None = None
    next_retry_at: str | None = None
    total_runs: int = 0
    total_failures: int = 0
    total_successes: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    # Cap in-memory history to avoid unbounded growth
    MAX_HISTORY: int = 50

    def record(self, execution: JobExecution) -> None:
        self.history.append(asdict(execution))
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

_registry = None  # set by JobManager.init_app


def _make_metrics(registry=None):
    return {
        "executions": Counter(
            "finmind_job_executions_total",
            "Total job executions by job and status.",
            ["job_id", "status"],
            registry=registry,
        ),
        "retries": Counter(
            "finmind_job_retries_total",
            "Total retry attempts by job.",
            ["job_id"],
            registry=registry,
        ),
        "dead_letters": Counter(
            "finmind_job_dead_letters_total",
            "Jobs that exhausted all retries.",
            ["job_id"],
            registry=registry,
        ),
        "duration": Histogram(
            "finmind_job_duration_seconds",
            "Job execution duration.",
            ["job_id"],
            buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
            registry=registry,
        ),
        "active": Gauge(
            "finmind_jobs_active",
            "Number of currently running jobs.",
            registry=registry,
        ),
    }


# ---------------------------------------------------------------------------
# Job Manager
# ---------------------------------------------------------------------------

class JobManager:
    """Singleton-style manager wired into a Flask app."""

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler | None = None
        self._states: dict[str, JobState] = {}
        self._retry_policies: dict[str, RetryPolicy] = {}
        self._original_funcs: dict[str, Callable] = {}
        self._redis = None
        self._metrics: dict | None = None
        self._app = None

    # -- Flask integration --------------------------------------------------

    def init_app(self, app, redis_client=None, registry=None) -> None:
        """Bind to a Flask app, optionally with Redis for persistence."""
        self._app = app
        self._redis = redis_client
        self._metrics = _make_metrics(registry)
        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,           # merge missed runs
                "max_instances": 1,         # no overlapping
                "misfire_grace_time": 60,   # 60s grace for missed
            },
            timezone="UTC",
        )
        self._scheduler.add_listener(self._on_event,
                                     EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
        self._restore_state()
        app.extensions["job_manager"] = self

    # -- Public API ---------------------------------------------------------

    def add_job(
        self,
        func: Callable,
        job_id: str,
        trigger: str = "interval",
        retry_policy: RetryPolicy | None = None,
        **trigger_kwargs,
    ) -> None:
        """Register a managed job with retry support."""
        policy = retry_policy or RetryPolicy()
        self._retry_policies[job_id] = policy
        self._original_funcs[job_id] = func

        if job_id not in self._states:
            self._states[job_id] = JobState(job_id=job_id)

        # Wrap the function to inject retry / monitoring logic
        wrapped = self._wrap(func, job_id, policy)

        self._scheduler.add_job(
            wrapped,
            trigger,
            id=job_id,
            replace_existing=True,
            **trigger_kwargs,
        )
        logger.info("Registered job %s (trigger=%s, max_retries=%d)",
                     job_id, trigger, policy.max_retries)

    def start(self) -> None:
        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("Job scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            self._persist_state()
            logger.info("Job scheduler shut down")

    def get_status(self) -> dict[str, Any]:
        """Return health-check / monitoring data for all managed jobs."""
        result = {}
        for jid, state in self._states.items():
            policy = self._retry_policies.get(jid, RetryPolicy())
            result[jid] = {
                "status": state.last_status,
                "attempt": state.attempt,
                "max_retries": policy.max_retries,
                "total_runs": state.total_runs,
                "total_successes": state.total_successes,
                "total_failures": state.total_failures,
                "last_error": state.last_error,
                "last_run_at": state.last_run_at,
                "next_retry_at": state.next_retry_at,
                "recent_history": state.history[-10:],
            }
        return result

    def get_dead_letters(self) -> list[dict[str, Any]]:
        """Return jobs that exhausted retries (for operator review)."""
        dead = []
        for jid, state in self._states.items():
            if state.last_status == JobStatus.FAILED.value:
                dead.append({
                    "job_id": jid,
                    "last_error": state.last_error,
                    "total_failures": state.total_failures,
                    "last_run_at": state.last_run_at,
                })
        return dead

    def reset_job(self, job_id: str) -> bool:
        """Reset a dead-lettered job so it will retry on next trigger."""
        state = self._states.get(job_id)
        if not state:
            return False
        state.attempt = 0
        state.last_status = JobStatus.PENDING.value
        state.last_error = None
        state.next_retry_at = None
        self._persist_state()
        logger.info("Reset job %s from dead-letter", job_id)
        return True

    # -- Internal -----------------------------------------------------------

    def _wrap(self, func: Callable, job_id: str, policy: RetryPolicy) -> Callable:
        """Return a wrapper that handles retry + metrics."""
        @functools.wraps(func)
        def _execute():
            state = self._states[job_id]

            # Skip if dead-lettered (until manually reset)
            if state.last_status == JobStatus.FAILED.value:
                return

            state.last_status = JobStatus.RUNNING.value
            state.total_runs += 1
            started = datetime.now(timezone.utc)
            if self._metrics:
                self._metrics["active"].inc()

            try:
                # Run inside app context if available
                if self._app:
                    with self._app.app_context():
                        func()
                else:
                    func()

                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                state.last_status = JobStatus.SUCCESS.value
                state.attempt = 0
                state.last_error = None
                state.next_retry_at = None
                state.total_successes += 1
                state.last_run_at = started.isoformat()

                execution = JobExecution(
                    job_id=job_id,
                    attempt=state.attempt,
                    status=JobStatus.SUCCESS.value,
                    started_at=started.isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=round(elapsed, 4),
                )
                state.record(execution)

                if self._metrics:
                    self._metrics["executions"].labels(job_id=job_id, status="success").inc()
                    self._metrics["duration"].labels(job_id=job_id).observe(elapsed)

                logger.info("Job %s succeeded in %.3fs", job_id, elapsed)

            except Exception as exc:
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                state.attempt += 1
                state.last_error = f"{type(exc).__name__}: {exc}"
                state.total_failures += 1
                state.last_run_at = started.isoformat()
                tb = traceback.format_exc()

                execution = JobExecution(
                    job_id=job_id,
                    attempt=state.attempt,
                    status=JobStatus.RETRYING.value if state.attempt < policy.max_retries else JobStatus.FAILED.value,
                    started_at=started.isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=round(elapsed, 4),
                    error=state.last_error,
                )
                state.record(execution)

                if self._metrics:
                    self._metrics["executions"].labels(job_id=job_id, status="error").inc()
                    self._metrics["duration"].labels(job_id=job_id).observe(elapsed)

                if state.attempt >= policy.max_retries:
                    # Dead-letter
                    state.last_status = JobStatus.FAILED.value
                    state.next_retry_at = None
                    if self._metrics:
                        self._metrics["dead_letters"].labels(job_id=job_id).inc()
                    logger.error(
                        "Job %s dead-lettered after %d attempts: %s\n%s",
                        job_id, state.attempt, exc, tb,
                    )
                else:
                    # Schedule retry
                    delay = policy.delay_for_attempt(state.attempt)
                    retry_at = datetime.now(timezone.utc)
                    state.last_status = JobStatus.RETRYING.value
                    state.next_retry_at = retry_at.isoformat()
                    if self._metrics:
                        self._metrics["retries"].labels(job_id=job_id).inc()
                    logger.warning(
                        "Job %s failed (attempt %d/%d), retrying in %.1fs: %s",
                        job_id, state.attempt, policy.max_retries, delay, exc,
                    )
                    # One-shot retry
                    self._scheduler.add_job(
                        _execute,
                        "date",
                        id=f"{job_id}__retry_{state.attempt}",
                        run_date=datetime.fromtimestamp(
                            time.time() + delay, tz=timezone.utc
                        ),
                        replace_existing=True,
                    )
            finally:
                if self._metrics:
                    self._metrics["active"].dec()
                self._persist_state()

        return _execute

    def _on_event(self, event) -> None:
        """Handle APScheduler lifecycle events (missed jobs)."""
        if event.code == EVENT_JOB_MISSED:
            job_id = event.job_id
            if job_id.endswith("__retry"):
                return  # ignore missed retries
            state = self._states.get(job_id)
            if state:
                state.last_status = JobStatus.MISSED.value
                logger.warning("Job %s missed its scheduled run", job_id)
                if self._metrics:
                    self._metrics["executions"].labels(job_id=job_id, status="missed").inc()

    # -- Redis persistence --------------------------------------------------

    _REDIS_KEY = "finmind:job_manager:state"

    def _persist_state(self) -> None:
        if not self._redis:
            return
        try:
            payload = {}
            for jid, state in self._states.items():
                payload[jid] = asdict(state)
            self._redis.set(self._REDIS_KEY, json.dumps(payload), ex=86400 * 7)
        except Exception:
            logger.debug("Failed to persist job state to Redis", exc_info=True)

    def _restore_state(self) -> None:
        if not self._redis:
            return
        try:
            raw = self._redis.get(self._REDIS_KEY)
            if raw:
                data = json.loads(raw)
                for jid, sdict in data.items():
                    history = sdict.pop("history", [])
                    sdict.pop("MAX_HISTORY", None)
                    state = JobState(**sdict)
                    state.history = history
                    # Reset running state on crash recovery
                    if state.last_status == JobStatus.RUNNING.value:
                        state.last_status = JobStatus.RETRYING.value
                    self._states[jid] = state
                logger.info("Restored job state for %d jobs from Redis", len(data))
        except Exception:
            logger.debug("Failed to restore job state from Redis", exc_info=True)


# Module-level singleton
job_manager = JobManager()
