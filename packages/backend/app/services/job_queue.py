"""Resilient background job queue built on Redis.

Provides job registration with configurable retry policies, automatic
retries with exponential/linear backoff, dead-letter queue for permanently
failed jobs, state tracking, timeout handling, and idempotency support.

Usage::

    from app.services.job_queue import JobQueue, RetryPolicy

    queue = JobQueue()

    # Register a handler
    @queue.handler("send_reminder")
    def handle_send_reminder(payload: dict) -> dict:
        # do work ...
        return {"status": "sent"}

    # Enqueue a job
    job_id = queue.enqueue(
        "send_reminder",
        payload={"reminder_id": 42},
        retry_policy=RetryPolicy(max_retries=3, backoff="exponential"),
    )

    # Process jobs (run in a worker loop or thread)
    queue.process_next()
"""

from __future__ import annotations

import json
import logging
import math
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

from ..extensions import redis_client

logger = logging.getLogger("finmind.jobs")

# ---------------------------------------------------------------------------
# Redis key prefixes
# ---------------------------------------------------------------------------
_PREFIX = "finmind:jobs"
_QUEUE_KEY = f"{_PREFIX}:queue"  # sorted set (score = enqueue timestamp)
_JOB_KEY = f"{_PREFIX}:job"  # hash per job  -> {_JOB_KEY}:<job_id>
_DLQ_KEY = f"{_PREFIX}:dlq"  # sorted set (score = dead timestamp)
_METRICS_KEY = f"{_PREFIX}:metrics"  # hash of counters
_ACTIVE_KEY = f"{_PREFIX}:active"  # set of currently-running job ids
_COMPLETED_KEY = f"{_PREFIX}:completed"  # sorted set (recent successes)


class JobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEAD = "DEAD"


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff: str = "exponential"  # "exponential" | "linear"
    base_delay: float = 2.0  # seconds
    max_delay: float = 300.0  # cap at 5 minutes

    def delay_for(self, attempt: int) -> float:
        """Compute delay in seconds for the given attempt (1-indexed)."""
        if self.backoff == "exponential":
            delay = self.base_delay * (2 ** (attempt - 1))
        else:  # linear
            delay = self.base_delay * attempt
        return min(delay, self.max_delay)


DEFAULT_RETRY = RetryPolicy()


@dataclass
class Job:
    id: str
    job_type: str
    payload: dict
    state: str = JobState.PENDING.value
    retry_policy: dict = field(default_factory=lambda: asdict(DEFAULT_RETRY))
    attempts: int = 0
    max_retries: int = 3
    created_at: float = 0.0
    updated_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    result: dict | None = None
    timeout: int = 300  # seconds

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        # JSON-stored fields
        for fld in ("payload", "retry_policy", "result"):
            if fld in data and isinstance(data[fld], str):
                data[fld] = json.loads(data[fld])
        # Numeric fields
        for fld in (
            "attempts",
            "max_retries",
            "timeout",
        ):
            if fld in data and isinstance(data[fld], str):
                data[fld] = int(data[fld])
        for fld in ("created_at", "updated_at", "started_at", "completed_at"):
            if fld in data and isinstance(data[fld], str):
                data[fld] = float(data[fld]) if data[fld] else None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class JobQueue:
    """Lightweight Redis-backed job queue with retry & dead-letter support."""

    def __init__(self, redis=None):
        self._redis = redis or redis_client
        self._handlers: dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------
    def handler(self, job_type: str):
        """Decorator to register a job handler function."""

        def decorator(fn: Callable):
            self._handlers[job_type] = fn
            return fn

        return decorator

    def register_handler(self, job_type: str, fn: Callable):
        """Programmatic handler registration."""
        self._handlers[job_type] = fn

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------
    def enqueue(
        self,
        job_type: str,
        payload: dict | None = None,
        retry_policy: RetryPolicy | None = None,
        job_id: str | None = None,
        timeout: int = 300,
        delay: float = 0,
    ) -> str:
        """Add a job to the queue.

        Args:
            job_type: Registered handler name.
            payload: Arbitrary JSON-serialisable data for the handler.
            retry_policy: Retry configuration. Defaults to 3 retries / exponential.
            job_id: Optional explicit ID for idempotency. If a job with this
                    ID already exists *and* is not in a terminal state, the
                    call is a no-op and returns the existing ID.
            timeout: Max seconds a single execution may take.
            delay: Seconds to wait before the job becomes eligible.

        Returns:
            The job ID (new or existing).
        """
        policy = retry_policy or DEFAULT_RETRY
        now = time.time()

        # Idempotency check
        if job_id:
            existing = self._redis.hgetall(f"{_JOB_KEY}:{job_id}")
            if existing:
                state = existing.get("state", "")
                if state not in (JobState.SUCCESS.value, JobState.DEAD.value):
                    logger.debug("Idempotent skip: job %s already in state %s", job_id, state)
                    return job_id

        jid = job_id or uuid.uuid4().hex
        job = Job(
            id=jid,
            job_type=job_type,
            payload=payload or {},
            state=JobState.PENDING.value,
            retry_policy=asdict(policy),
            max_retries=policy.max_retries,
            created_at=now,
            updated_at=now,
            timeout=timeout,
        )
        # Store job data as a Redis hash
        store = {}
        for k, v in job.to_dict().items():
            if isinstance(v, dict):
                store[k] = json.dumps(v)
            elif v is None:
                continue
            else:
                store[k] = str(v)
        self._redis.hset(f"{_JOB_KEY}:{jid}", mapping=store)

        # Add to queue sorted set (score = eligible-at timestamp)
        score = now + delay
        self._redis.zadd(_QUEUE_KEY, {jid: score})
        self._increment_metric("enqueued")
        logger.info("Enqueued job %s type=%s", jid, job_type)
        return jid

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process_next(self) -> bool:
        """Pop and execute the next eligible job.

        Returns True if a job was processed, False if the queue was empty.
        """
        now = time.time()

        # Atomically pop the oldest eligible job
        items = self._redis.zrangebyscore(_QUEUE_KEY, "-inf", now, start=0, num=1)
        if not items:
            return False

        job_id = items[0]
        # Remove from queue (atomic check — another worker may have grabbed it)
        removed = self._redis.zrem(_QUEUE_KEY, job_id)
        if not removed:
            return False  # another worker got it

        raw = self._redis.hgetall(f"{_JOB_KEY}:{job_id}")
        if not raw:
            return False

        job = Job.from_dict(raw)
        handler = self._handlers.get(job.job_type)
        if not handler:
            logger.error("No handler for job type %s (job %s)", job.job_type, job_id)
            self._move_to_dlq(job, f"No handler registered for type '{job.job_type}'")
            return True

        # Mark running
        job.state = JobState.RUNNING.value
        job.attempts += 1
        job.started_at = now
        job.updated_at = now
        self._save_job(job)
        self._redis.sadd(_ACTIVE_KEY, job_id)

        try:
            result = self._execute_with_timeout(handler, job)
            self._on_success(job, result)
        except Exception as exc:
            self._on_failure(job, exc)

        self._redis.srem(_ACTIVE_KEY, job_id)
        return True

    def process_batch(self, max_jobs: int = 10) -> int:
        """Process up to *max_jobs* eligible jobs. Returns count processed."""
        processed = 0
        for _ in range(max_jobs):
            if not self.process_next():
                break
            processed += 1
        return processed

    # ------------------------------------------------------------------
    # Manual retry
    # ------------------------------------------------------------------
    def retry_job(self, job_id: str) -> bool:
        """Manually re-enqueue a failed or dead job."""
        raw = self._redis.hgetall(f"{_JOB_KEY}:{job_id}")
        if not raw:
            return False
        job = Job.from_dict(raw)
        if job.state not in (JobState.FAILED.value, JobState.DEAD.value):
            return False
        # Reset for retry
        job.state = JobState.PENDING.value
        job.error = None
        job.updated_at = time.time()
        self._save_job(job)
        self._redis.zrem(_DLQ_KEY, job_id)
        self._redis.zadd(_QUEUE_KEY, {job_id: time.time()})
        self._increment_metric("manual_retries")
        logger.info("Manual retry for job %s", job_id)
        return True

    # ------------------------------------------------------------------
    # Dead-letter queue
    # ------------------------------------------------------------------
    def list_dead_letter(self, limit: int = 50) -> list[dict]:
        """Return dead-letter jobs, newest first."""
        ids = self._redis.zrevrange(_DLQ_KEY, 0, limit - 1)
        jobs = []
        for jid in ids:
            raw = self._redis.hgetall(f"{_JOB_KEY}:{jid}")
            if raw:
                jobs.append(Job.from_dict(raw).to_dict())
        return jobs

    def clear_dead_letter(self, job_id: str) -> bool:
        """Remove a job from the dead-letter queue and clean up its data."""
        removed = self._redis.zrem(_DLQ_KEY, job_id)
        if removed:
            self._redis.delete(f"{_JOB_KEY}:{job_id}")
            logger.info("Cleared dead-letter job %s", job_id)
        return bool(removed)

    # ------------------------------------------------------------------
    # Status / metrics
    # ------------------------------------------------------------------
    def get_job(self, job_id: str) -> dict | None:
        raw = self._redis.hgetall(f"{_JOB_KEY}:{job_id}")
        if not raw:
            return None
        return Job.from_dict(raw).to_dict()

    def queue_depth(self) -> int:
        return self._redis.zcard(_QUEUE_KEY)

    def active_count(self) -> int:
        return self._redis.scard(_ACTIVE_KEY)

    def dlq_count(self) -> int:
        return self._redis.zcard(_DLQ_KEY)

    def completed_count(self) -> int:
        return self._redis.zcard(_COMPLETED_KEY)

    def get_metrics(self) -> dict[str, int]:
        raw = self._redis.hgetall(_METRICS_KEY)
        return {k: int(v) for k, v in raw.items()}

    def list_failed(self, limit: int = 50) -> list[dict]:
        """Return failed jobs (both retrying and dead-letter), newest first."""
        # Combine DLQ with any jobs still in FAILED state waiting for retry
        dlq_ids = self._redis.zrevrange(_DLQ_KEY, 0, limit - 1)
        jobs = []
        seen = set()
        for jid in dlq_ids:
            raw = self._redis.hgetall(f"{_JOB_KEY}:{jid}")
            if raw:
                jobs.append(Job.from_dict(raw).to_dict())
                seen.add(jid)

        # Also scan queue for FAILED-state jobs awaiting retry
        queue_ids = self._redis.zrange(_QUEUE_KEY, 0, -1)
        for jid in queue_ids:
            if jid in seen:
                continue
            raw = self._redis.hgetall(f"{_JOB_KEY}:{jid}")
            if raw and raw.get("state") == JobState.FAILED.value:
                jobs.append(Job.from_dict(raw).to_dict())
                seen.add(jid)
            if len(jobs) >= limit:
                break
        return jobs

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _execute_with_timeout(self, handler: Callable, job: Job) -> Any:
        """Execute handler. Timeout enforcement via signal is Unix-only;
        we use a simple wall-clock check for portability."""
        start = time.time()
        result = handler(job.payload)
        elapsed = time.time() - start
        if elapsed > job.timeout:
            raise TimeoutError(
                f"Job {job.id} exceeded timeout ({elapsed:.1f}s > {job.timeout}s)"
            )
        return result

    def _on_success(self, job: Job, result: Any):
        now = time.time()
        duration = now - (job.started_at or now)
        job.state = JobState.SUCCESS.value
        job.result = result if isinstance(result, dict) else {"result": str(result)}
        job.completed_at = now
        job.updated_at = now
        self._save_job(job)
        self._redis.zadd(_COMPLETED_KEY, {job.id: now})
        # Trim completed list to last 1000
        self._redis.zremrangebyrank(_COMPLETED_KEY, 0, -1001)
        self._increment_metric("succeeded")
        self._record_duration(duration)
        logger.info("Job %s succeeded in %.2fs", job.id, duration)

    def _on_failure(self, job: Job, exc: Exception):
        now = time.time()
        error_msg = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        logger.warning("Job %s failed (attempt %d): %s", job.id, job.attempts, error_msg)

        policy = RetryPolicy(**job.retry_policy)
        if job.attempts < job.max_retries:
            # Schedule retry with backoff
            delay = policy.delay_for(job.attempts)
            job.state = JobState.FAILED.value
            job.error = error_msg
            job.updated_at = now
            self._save_job(job)
            self._redis.zadd(_QUEUE_KEY, {job.id: now + delay})
            self._increment_metric("retries")
            logger.info(
                "Job %s scheduled for retry in %.1fs (attempt %d/%d)",
                job.id,
                delay,
                job.attempts,
                job.max_retries,
            )
        else:
            self._move_to_dlq(job, error_msg)

    def _move_to_dlq(self, job: Job, error: str):
        now = time.time()
        job.state = JobState.DEAD.value
        job.error = error
        job.completed_at = now
        job.updated_at = now
        self._save_job(job)
        self._redis.zadd(_DLQ_KEY, {job.id: now})
        self._increment_metric("dead")
        logger.error("Job %s moved to dead-letter queue: %s", job.id, error)

    def _save_job(self, job: Job):
        store = {}
        for k, v in job.to_dict().items():
            if isinstance(v, dict):
                store[k] = json.dumps(v)
            elif v is None:
                continue
            else:
                store[k] = str(v)
        self._redis.hset(f"{_JOB_KEY}:{job.id}", mapping=store)

    def _increment_metric(self, name: str, amount: int = 1):
        self._redis.hincrby(_METRICS_KEY, name, amount)

    def _record_duration(self, duration: float):
        """Track total duration and count for average computation."""
        pipe = self._redis.pipeline()
        pipe.hincrbyfloat(_METRICS_KEY, "total_duration", round(duration, 4))
        pipe.hincrby(_METRICS_KEY, "duration_count", 1)
        pipe.execute()

    def flush_all(self):
        """Remove all job data from Redis. For testing only."""
        keys = self._redis.keys(f"{_PREFIX}:*")
        if keys:
            self._redis.delete(*keys)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
job_queue = JobQueue()
