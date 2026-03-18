"""Reminder job handlers — bridges the job queue with reminder delivery.

Registers a ``send_reminder`` job type that processes reminder dispatch
through the resilient job queue with automatic retries.
"""

from __future__ import annotations

import logging

from ..extensions import db
from ..models import Reminder
from ..observability import track_reminder_event
from .job_queue import RetryPolicy, job_queue
from .reminders import send_reminder as _deliver_reminder

logger = logging.getLogger("finmind.reminder_jobs")


# ---------------------------------------------------------------------------
# Register the handler
# ---------------------------------------------------------------------------
@job_queue.handler("send_reminder")
def handle_send_reminder(payload: dict) -> dict:
    """Process a single reminder delivery via the job queue.

    Payload:
        reminder_id (int): ID of the Reminder row to dispatch.
    """
    reminder_id = payload.get("reminder_id")
    if not reminder_id:
        raise ValueError("Missing reminder_id in payload")

    reminder = db.session.get(Reminder, reminder_id)
    if not reminder:
        raise ValueError(f"Reminder {reminder_id} not found")

    if reminder.sent:
        logger.info("Reminder %d already sent, skipping", reminder_id)
        return {"status": "skipped", "reason": "already_sent"}

    success = _deliver_reminder(reminder)
    if not success:
        raise RuntimeError(f"Failed to deliver reminder {reminder_id} via {reminder.channel}")

    reminder.sent = True
    db.session.commit()

    try:
        track_reminder_event(event="sent", channel=reminder.channel)
    except RuntimeError:
        # Outside request context (worker process) — skip metrics
        pass

    logger.info("Reminder %d delivered via %s", reminder_id, reminder.channel)
    return {"status": "sent", "reminder_id": reminder_id, "channel": reminder.channel}


# ---------------------------------------------------------------------------
# Helper to enqueue a reminder through the job queue
# ---------------------------------------------------------------------------
def enqueue_reminder(
    reminder_id: int,
    max_retries: int = 3,
    backoff: str = "exponential",
) -> str:
    """Enqueue a reminder for delivery through the resilient job queue.

    Uses the reminder ID as the job ID for idempotency — the same reminder
    won't be enqueued twice while it's still pending or running.

    Returns:
        The job ID.
    """
    job_id = f"reminder:{reminder_id}"
    return job_queue.enqueue(
        "send_reminder",
        payload={"reminder_id": reminder_id},
        retry_policy=RetryPolicy(max_retries=max_retries, backoff=backoff),
        job_id=job_id,
        timeout=60,
    )
