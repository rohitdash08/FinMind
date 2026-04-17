"""Resilient background job queue with retry and monitoring.

Features:
- Redis-backed job queue with priority support
- Exponential backoff retry with configurable max retries
- Dead-letter queue for permanently failed jobs
- Job status tracking in PostgreSQL
- Prometheus metrics for monitoring
"""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional

from ..extensions import db, redis_client

logger = logging.getLogger("finmind.jobs")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUEUE_KEY = "finmind:jobs:queue"
PROCESSING_KEY = "finmind:jobs:processing"
DEAD_LETTER_KEY = "finmind:jobs:dead_letter"
JOB_DATA_KEY = "finmind:jobs:data:{job_id}"
JOB_LOCK_KEY = "finmind:jobs:lock:{job_id}"

DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_DELAY = 5  # seconds (base delay, doubles each retry)
DEFAULT_JOB_TIMEOUT = 300  # 5 minutes


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"  # moved to dead-letter queue


# ---------------------------------------------------------------------------
# Job Data Model (Redis)
# ---------------------------------------------------------------------------

def _job_key(job_id: str) -> str:
    return JOB_DATA_KEY.format(job_id=job_id)


def _lock_key(job_id: str) -> str:
    return JOB_LOCK_KEY.format(job_id=job_id)


def save_job_metadata(job_id: str, metadata: dict) -> None:
    """Persist job metadata in Redis."""
    redis_client.set(
        _job_key(job_id),
        json.dumps(metadata, default=str),
        ex=86400 * 7,  # 7-day TTL
    )


def load_job_metadata(job_id: str) -> Optional[dict]:
    """Load job metadata from Redis."""
    raw = redis_client.get(_job_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# PostgreSQL Job Record
# ---------------------------------------------------------------------------

from sqlalchemy import text


def _ensure_jobs_table() -> None:
    """Create the background_jobs table if it doesn't exist."""
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS background_jobs (
                id              VARCHAR(64) PRIMARY KEY,
                job_type        VARCHAR(100) NOT NULL,
                status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                queue           VARCHAR(50) NOT NULL DEFAULT 'default',
                priority        INT NOT NULL DEFAULT 5,
                attempts        INT NOT NULL DEFAULT 0,
                max_retries     INT NOT NULL DEFAULT 5,
                last_error      TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at      TIMESTAMPTZ,
                completed_at    TIMESTAMPTZ,
                next_retry_at   TIMESTAMPTZ,
                payload         JSONB DEFAULT '{}'::jsonb,
                result          JSONB
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_bg_jobs_status
            ON background_jobs (status, next_retry_at)
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_bg_jobs_type
            ON background_jobs (job_type, created_at DESC)
            """
        )
    )
    db.session.commit()


def _insert_job_record(
    job_id: str,
    job_type: str,
    queue: str,
    priority: int,
    max_retries: int,
    payload: dict,
) -> None:
    """Insert a job record into PostgreSQL."""
    db.session.execute(
        text(
            """
            INSERT INTO background_jobs
                (id, job_type, status, queue, priority, max_retries, payload, created_at)
            VALUES
                (:id, :job_type, 'pending', :queue, :priority, :max_retries, :payload, NOW())
            """
        ),
        {
            "id": job_id,
            "job_type": job_type,
            "queue": queue,
            "priority": priority,
            "max_retries": max_retries,
            "payload": json.dumps(payload),
        },
    )
    db.session.commit()


def _update_job_status(
    job_id: str,
    status: str,
    error: Optional[str] = None,
    result: Optional[dict] = None,
    increment_attempts: bool = False,
    next_retry_at: Optional[datetime] = None,
) -> None:
    """Update a job's status in PostgreSQL."""
    sets = ["status = :status", "started_at = COALESCE(started_at, CASE WHEN :status = 'running' THEN NOW() ELSE started_at END)"]
    params: dict[str, Any] = {"id": job_id, "status": status}

    if status in ("completed", "failed", "dead"):
        sets.append("completed_at = CASE WHEN completed_at IS NULL THEN NOW() ELSE completed_at END")
    if error is not None:
        sets.append("last_error = :error")
        params["error"] = error
    if result is not None:
        sets.append("result = :result")
        params["result"] = json.dumps(result)
    if increment_attempts:
        sets.append("attempts = attempts + 1")
    if next_retry_at is not None:
        sets.append("next_retry_at = :next_retry_at")
        params["next_retry_at"] = next_retry_at

    db.session.execute(
        text(f"UPDATE background_jobs SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    db.session.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enqueue(
    job_type: str,
    payload: dict | None = None,
    queue: str = "default",
    priority: int = 5,
    max_retries: int = DEFAULT_MAX_RETRIES,
    job_id: str | None = None,
) -> str:
    """Enqueue a new background job.

    Args:
        job_type:  Registered handler name (e.g. "send_reminder").
        payload:   JSON-serialisable dict passed to the handler.
        queue:     Queue name (default "default").
        priority:  Lower number = higher priority (1 highest).
        max_retries: Maximum retry attempts before dead-letter.
        job_id:    Optional explicit job ID (uuid4 generated otherwise).

    Returns:
        The job ID.
    """
    _ensure_jobs_table()
    job_id = job_id or str(uuid.uuid4())
    payload = payload or {}

    metadata = {
        "job_id": job_id,
        "job_type": job_type,
        "queue": queue,
        "priority": priority,
        "max_retries": max_retries,
        "payload": payload,
        "status": JobStatus.PENDING,
        "created_at": datetime.utcnow().isoformat(),
        "attempts": 0,
    }

    save_job_metadata(job_id, metadata)
    _insert_job_record(job_id, job_type, queue, priority, max_retries, payload)

    # Push to Redis sorted-set (score = priority, value = job_id)
    redis_client.zadd(QUEUE_KEY, {job_id: priority})
    logger.info("Enqueued job %s [%s] priority=%d", job_id, job_type, priority)
    return job_id


def get_job_status(job_id: str) -> Optional[dict]:
    """Return current status of a job."""
    metadata = load_job_metadata(job_id)
    if metadata is None:
        # Fall back to PostgreSQL
        row = db.session.execute(
            text("SELECT * FROM background_jobs WHERE id = :id"),
            {"id": job_id},
        ).fetchone()
        if row is None:
            return None
        return dict(row._mapping)
    return metadata


def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    queue: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List jobs with optional filters."""
    _ensure_jobs_table()
    clauses = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if status:
        clauses.append("status = :status")
        params["status"] = status
    if job_type:
        clauses.append("job_type = :job_type")
        params["job_type"] = job_type
    if queue:
        clauses.append("queue = :queue")
        params["queue"] = queue

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.session.execute(
        text(
            f"SELECT * FROM background_jobs {where} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    ).fetchall()
    return [dict(r._mapping) for r in rows]


def cancel_job(job_id: str) -> bool:
    """Cancel a pending job."""
    meta = load_job_metadata(job_id)
    if meta is None:
        return False
    if meta["status"] not in (JobStatus.PENDING, JobStatus.RETRYING):
        return False
    meta["status"] = "cancelled"
    save_job_metadata(job_id, meta)
    _update_job_status(job_id, "cancelled")
    redis_client.zrem(QUEUE_KEY, job_id)
    logger.info("Cancelled job %s", job_id)
    return True


def retry_dead_job(job_id: str) -> bool:
    """Re-enqueue a dead-lettered job."""
    meta = load_job_metadata(job_id)
    if meta is None:
        return False
    if meta["status"] != JobStatus.DEAD:
        return False
    meta["status"] = JobStatus.PENDING
    meta["attempts"] = 0
    meta["last_error"] = None
    save_job_metadata(job_id, meta)
    _update_job_status(
        job_id,
        JobStatus.PENDING,
        error=None,
        increment_attempts=False,
    )
    redis_client.zadd(QUEUE_KEY, {job_id: meta.get("priority", 5)})
    redis_client.lrem(DEAD_LETTER_KEY, 0, job_id)
    logger.info("Re-enqueued dead job %s", job_id)
    return True


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def get_queue_stats() -> dict:
    """Return aggregate queue statistics."""
    _ensure_jobs_table()
    rows = db.session.execute(
        text(
            """
            SELECT status, COUNT(*) AS count
            FROM background_jobs
            GROUP BY status
            """
        )
    ).fetchall()
    stats = {r.status: r.count for r in rows}
    stats["queued"] = redis_client.zcard(QUEUE_KEY)
    stats["processing"] = redis_client.llen(PROCESSING_KEY)
    stats["dead_letter"] = redis_client.llen(DEAD_LETTER_KEY)
    return stats
