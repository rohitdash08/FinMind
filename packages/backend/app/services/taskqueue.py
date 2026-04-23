"""Lightweight Redis-backed task queue with retry logic and dead-letter handling.

Design:
- Tasks are persisted in SQLAlchemy (ground truth) *and* tracked in Redis sorted
  sets for fast queue operations.
- Redis keys:
    taskq:pending   — sorted set scored by scheduled_at timestamp
    taskq:running   — set of currently-processing task ids
    taskq:dead      — list of permanently-failed task ids
- Worker loop: pull due tasks from ``taskq:pending``, run them, handle
  success / retry / dead-letter.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..extensions import db, redis_client
from ..models import Task, TaskStatus

logger = logging.getLogger("finmind.taskqueue")

# Redis key constants
_PENDING_KEY = "taskq:pending"
_RUNNING_KEY = "taskq:running"
_DEAD_KEY = "taskq:dead"

# Default retry settings
DEFAULT_MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 30  # first retry after 30 s, then 60, 120, …


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


def enqueue(
    task_type: str,
    payload: dict[str, Any] | None = None,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    scheduled_at: datetime | None = None,
) -> Task:
    """Create a task and push it onto the pending queue."""
    run_at = scheduled_at or datetime.now(timezone.utc)
    score = run_at.timestamp()

    task = Task(
        task_type=task_type,
        payload=json.dumps(payload or {}),
        status=TaskStatus.PENDING,
        max_retries=max_retries,
        scheduled_at=run_at,
    )
    db.session.add(task)
    db.session.flush()  # assign id

    redis_client.zadd(_PENDING_KEY, {str(task.id): score})
    logger.info(
        "Enqueued task id=%s type=%s scheduled_at=%s",
        task.id, task.task_type, run_at.isoformat(),
    )
    return task


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

# Registry: task_type → callable(payload_dict) → bool (True = success)
_HANDLERS: dict[str, Callable[[dict], bool]] = {}


def register_handler(task_type: str, fn: Callable[[dict], bool]) -> None:
    _HANDLERS[task_type] = fn


def get_handler(task_type: str) -> Callable[[dict], bool] | None:
    return _HANDLERS.get(task_type)


def process_next_tick() -> bool:
    """Try to claim and execute one due task.  Returns True if a task was run."""
    now_ts = datetime.now(timezone.utc).timestamp()

    # Fetch up to 1 task whose scheduled_at <= now
    candidates = redis_client.zrangebyscore(_PENDING_KEY, "-inf", now_ts, start=0, num=1)
    if not candidates:
        return False

    task_id_bytes = candidates[0]
    task_id = int(task_id_bytes)

    # Atomically move from pending → running (prevent duplicate claims)
    removed = redis_client.zrem(_PENDING_KEY, task_id_bytes)
    if not removed:
        return False  # another worker grabbed it

    redis_client.sadd(_RUNNING_KEY, task_id_bytes)

    task = db.session.get(Task, task_id)
    if task is None:
        redis_client.srem(_RUNNING_KEY, task_id_bytes)
        logger.warning("Task id=%s not found in DB; dropping from queue", task_id)
        return False

    handler = get_handler(task.task_type)
    if handler is None:
        logger.error("No handler registered for task_type=%s; dead-lettering id=%s", task.task_type, task_id)
        _mark_dead(task, f"No handler for task_type={task.task_type}")
        return True

    # Execute
    task.status = TaskStatus.RUNNING
    task.attempt += 1
    task.started_at = datetime.now(timezone.utc)
    db.session.commit()

    try:
        payload = json.loads(task.payload)
        success = handler(payload)
    except Exception as exc:
        success = False
        task.last_error = str(exc)[:2000]
        logger.exception("Task id=%s threw on attempt %s", task_id, task.attempt)

    if success:
        task.status = TaskStatus.SUCCESS
        task.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        redis_client.srem(_RUNNING_KEY, task_id_bytes)
        logger.info("Task id=%s succeeded on attempt %s", task_id, task.attempt)
    else:
        _handle_failure(task)

    return True


def _handle_failure(task: Task) -> None:
    """Retry with exponential back-off, or dead-letter."""
    if task.attempt < task.max_retries:
        backoff = BASE_BACKOFF_SECONDS * (2 ** (task.attempt - 1))
        next_run = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        task.status = TaskStatus.PENDING
        task.next_retry_at = next_run
        db.session.commit()

        # Re-enqueue in Redis
        redis_client.srem(_RUNNING_KEY, str(task.id))
        redis_client.zadd(_PENDING_KEY, {str(task.id): next_run.timestamp()})
        logger.info(
            "Task id=%s retry %s/%s, next at %s",
            task.id, task.attempt, task.max_retries, next_run.isoformat(),
        )
    else:
        _mark_dead(task, task.last_error or "Max retries exceeded")


def _mark_dead(task: Task, reason: str) -> None:
    task.status = TaskStatus.DEAD
    task.finished_at = datetime.now(timezone.utc)
    if not task.last_error:
        task.last_error = reason
    db.session.commit()
    redis_client.srem(_RUNNING_KEY, str(task.id))
    redis_client.rpush(_DEAD_KEY, str(task.id))
    logger.error("Task id=%s DEAD: %s", task.id, reason)


# ---------------------------------------------------------------------------
# Worker loop (call from CLI or thread)
# ---------------------------------------------------------------------------


def worker_loop(poll_interval: float = 1.0, max_iterations: int | None = None) -> None:
    """Blocking loop that continuously processes tasks."""
    logger.info("Task worker starting (poll_interval=%.1fs)", poll_interval)
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        did_work = process_next_tick()
        if not did_work:
            time.sleep(poll_interval)
        iteration += 1


# ---------------------------------------------------------------------------
# Monitoring helpers
# ---------------------------------------------------------------------------


def queue_stats() -> dict[str, int]:
    """Return counts for each queue and by-status."""
    pending = redis_client.zcard(_PENDING_KEY)
    running = redis_client.scard(_RUNNING_KEY)
    dead = redis_client.llen(_DEAD_KEY)

    # DB-level counts (more expensive, but accurate)
    from sqlalchemy import func
    status_counts = dict(
        db.session.query(Task.status, func.count(Task.id))
        .group_by(Task.status)
        .all()
    )
    serialised = {s.value if isinstance(s, TaskStatus) else s: c for s, c in status_counts.items()}

    return {
        "redis_pending": pending,
        "redis_running": running,
        "redis_dead": dead,
        "db_by_status": serialised,
    }


def retry_dead_task(task_id: int) -> bool:
    """Move a dead task back to the pending queue for one more attempt."""
    task = db.session.get(Task, task_id)
    if task is None or task.status != TaskStatus.DEAD:
        return False
    task.status = TaskStatus.PENDING
    task.attempt = 0
    task.last_error = None
    task.next_retry_at = None
    task.scheduled_at = datetime.now(timezone.utc)
    task.finished_at = None
    db.session.commit()

    # Remove from dead list (best-effort)
    redis_client.lrem(_DEAD_KEY, 0, str(task_id))
    redis_client.zadd(_PENDING_KEY, {str(task_id): task.scheduled_at.timestamp()})
    logger.info("Retried dead task id=%s", task_id)
    return True


def purge_dead_tasks(older_than_hours: int = 168) -> int:
    """Delete dead tasks older than *older_than_hours* (default 7 days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    count = Task.query.filter(
        Task.status == TaskStatus.DEAD,
        Task.finished_at < cutoff,
    ).delete()
    db.session.commit()
    logger.info("Purged %s dead tasks older than %sh", count, older_than_hours)
    return count
