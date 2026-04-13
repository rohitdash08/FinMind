"""Wraps reminder delivery in the background job framework."""
import logging

from ..extensions import db
from ..models import Reminder
from .jobs import register_handler
from .reminders import send_reminder

logger = logging.getLogger("finmind.reminder_jobs")


@register_handler("send_reminder")
def handle_send_reminder(payload: dict | None) -> dict:
    """Execute a single reminder send via the job framework.

    Expected payload: {"reminder_id": <int>}
    """
    if not payload or "reminder_id" not in payload:
        raise ValueError("payload must contain 'reminder_id'")

    reminder_id = payload["reminder_id"]
    reminder = db.session.get(Reminder, reminder_id)
    if reminder is None:
        raise ValueError(f"Reminder id={reminder_id} not found")

    if reminder.sent:
        logger.info("Reminder id=%s already sent, skipping", reminder_id)
        return {"skipped": True, "reason": "already_sent"}

    success = send_reminder(reminder)
    if not success:
        raise RuntimeError(f"Failed to deliver reminder id={reminder_id}")

    reminder.sent = True
    db.session.commit()
    logger.info("Reminder id=%s sent successfully via job", reminder_id)
    return {"sent": True, "reminder_id": reminder_id}
