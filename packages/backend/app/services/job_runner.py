"""
Resilient background job runner with exponential backoff retry.

Provides a generic job execution engine that wraps any callable with:
- Exponential backoff retry (configurable delays and max attempts)
- Per-item status tracking (pending → sending → sent | failed → dead)
- Dead-letter queue for permanently failed jobs
- Crash recovery for stale "sending" jobs
- Prometheus metrics integration
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_

from ..extensions import db
from ..models import Reminder
from ..observability import track_reminder_event
from ..services.reminders import send_reminder

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger("finmind.job_runner")

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """Configurable retry strategy with exponential backoff."""
    max_retries: int = 3
    base_delay_seconds: int = 60          # 1 minute
    backoff_factor: float = 3.0           # 1m → 3m → 9m
    max_delay_seconds: int = 3600         # cap at 1 hour
    stale_timeout_seconds: int = 600      # 10 min = stale

    def delay_for_attempt(self, attempt: int) -> int:
        """Calculate delay in seconds for the given attempt number."""
        delay = self.base_delay_seconds * (self.backoff_factor ** attempt)
        return min(int(delay), self.max_delay_seconds)


DEFAULT_POLICY = RetryPolicy()

# ---------------------------------------------------------------------------
# Run result tracking
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Captures statistics from a single scheduler run."""
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    dead_lettered: int = 0
    recovered: int = 0
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_due_reminders(
    batch_size: int = 50,
    policy: RetryPolicy | None = None,
) -> RunResult:
    """
    Process all due reminders across all users with retry logic.

    Improvements over the original ``/reminders/run`` endpoint:
    - Processes reminders for *all* users (no JWT scope)
    - Tracks individual success/failure per reminder
    - Applies exponential-backoff retry on failure
    - Dead-letters reminders that exceed ``max_retries``
    - Records per-item commit so crashes don't lose progress
    """
    pol = policy or DEFAULT_POLICY
    result = RunResult()
    start = time.monotonic()
    now = datetime.utcnow()

    # 1. Recover stale "sending" reminders (crash recovery)
    result.recovered = _recover_stale(now, pol)

    # 2. Fetch due reminders: pending (new) OR failed (retrying)
    reminders = (
        db.session.query(Reminder)
        .filter(
            Reminder.status.in_(["pending", "failed"]),
            Reminder.send_at <= now,
            or_(
                Reminder.next_retry_at.is_(None),
                Reminder.next_retry_at <= now,
            ),
            Reminder.retry_count < pol.max_retries,
        )
        .order_by(Reminder.send_at.asc())
        .limit(batch_size)
        .all()
    )

    for reminder in reminders:
        result.processed += 1
        _process_one(reminder, pol, result, now)

    result.duration_ms = round((time.monotonic() - start) * 1000, 2)
    logger.info(
        "Job run complete: processed=%d succeeded=%d failed=%d dead=%d recovered=%d duration_ms=%.1f",
        result.processed,
        result.succeeded,
        result.failed,
        result.dead_lettered,
        result.recovered,
        result.duration_ms,
    )
    return result


def _process_one(
    reminder: Reminder,
    policy: RetryPolicy,
    result: RunResult,
    now: datetime,
) -> None:
    """Attempt to deliver a single reminder with per-item commit."""
    reminder.status = "sending"
    reminder.started_at = now
    db.session.commit()

    try:
        success = send_reminder(reminder)
    except Exception as exc:
        _handle_failure(reminder, str(exc), policy, result)
        return

    if success:
        reminder.status = "sent"
        reminder.sent = True            # backward-compat with old boolean field
        reminder.completed_at = datetime.utcnow()
        reminder.last_error = None
        db.session.commit()
        result.succeeded += 1
        track_reminder_event(event="sent", channel=reminder.channel)
        logger.debug("Reminder %d sent successfully", reminder.id)
    else:
        _handle_failure(reminder, "delivery returned false", policy, result)


def _handle_failure(
    reminder: Reminder,
    error: str,
    policy: RetryPolicy,
    result: RunResult,
) -> None:
    """Transition a failed reminder to either *failed* (retry later) or *dead*."""
    reminder.retry_count += 1
    reminder.last_error = error[:500]

    if reminder.retry_count >= policy.max_retries:
        reminder.status = "dead"
        reminder.completed_at = datetime.utcnow()
        result.dead_lettered += 1
        track_reminder_event(
            event="dead_lettered", channel=reminder.channel, status="error"
        )
        logger.warning(
            "Reminder %d dead-lettered after %d retries: %s",
            reminder.id,
            reminder.retry_count,
            error,
        )
    else:
        delay = policy.delay_for_attempt(reminder.retry_count)
        reminder.status = "failed"
        reminder.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        result.failed += 1
        track_reminder_event(
            event="retry_scheduled", channel=reminder.channel, status="error"
        )
        logger.info(
            "Reminder %d failed (attempt %d/%d), retry in %ds: %s",
            reminder.id,
            reminder.retry_count,
            policy.max_retries,
            delay,
            error,
        )

    db.session.commit()


def _recover_stale(now: datetime, policy: RetryPolicy) -> int:
    """
    Mark reminders stuck in "sending" (older than stale_timeout) as failed.

    This handles the case where the process crashed mid-delivery.
    """
    cutoff = now - timedelta(seconds=policy.stale_timeout_seconds)
    stale = (
        db.session.query(Reminder)
        .filter(
            Reminder.status == "sending",
            Reminder.started_at <= cutoff,
        )
        .all()
    )
    for r in stale:
        r.status = "failed"
        r.last_error = "stale: process may have crashed during delivery"
        r.retry_count = min(r.retry_count + 1, r.retry_count)  # don't double-count
        logger.warning("Recovered stale reminder %d", r.id)
    if stale:
        db.session.commit()
    return len(stale)


# ---------------------------------------------------------------------------
# Dead-letter management
# ---------------------------------------------------------------------------

def retry_dead_letters(limit: int = 20) -> int:
    """
    Reset dead-lettered reminders for re-processing.

    Resets status to pending, clears retry count and error.
    Returns count of reminders reset.
    """
    items = (
        db.session.query(Reminder)
        .filter(Reminder.status == "dead")
        .order_by(Reminder.id.asc())
        .limit(limit)
        .all()
    )
    for r in items:
        r.status = "pending"
        r.retry_count = 0
        r.last_error = None
        r.next_retry_at = None
        r.started_at = None
        r.completed_at = None
    db.session.commit()
    logger.info("Reset %d dead-lettered reminders", len(items))
    return len(items)


def get_job_stats() -> dict:
    """Return aggregate statistics about reminder processing."""
    from sqlalchemy import func

    counts = dict(
        db.session.query(Reminder.status, func.count(Reminder.id))
        .group_by(Reminder.status)
        .all()
    )
    return {
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "dead": counts.get("dead", 0),
        "total": sum(counts.values()),
    }
