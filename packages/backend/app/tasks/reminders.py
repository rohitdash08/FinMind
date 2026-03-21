"""
Celery tasks for reminder notifications with resilient retry and monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from celery import Task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from ..celery_config import celery_app
from ..extensions import db, redis_client
from ..models import Reminder, NotificationLog
from ..services.reminders import send_email, send_whatsapp
from ..observability import track_reminder_event

logger = logging.getLogger("finmind.tasks.reminders")


class ReminderTask(Task):
    """Base task class for reminder operations with monitoring."""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure - log to dead letter queue."""
        reminder_id = args[0] if args else kwargs.get("reminder_id")
        logger.error(
            f"Reminder task {task_id} failed for reminder {reminder_id}: {exc}",
            extra={"task_id": task_id, "reminder_id": reminder_id, "error": str(exc)}
        )
        # Track failure metric
        if reminder_id:
            track_reminder_event("send", "unknown", "failed")
        super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        reminder_id = args[0] if args else kwargs.get("reminder_id")
        logger.info(
            f"Reminder task {task_id} succeeded for reminder {reminder_id}",
            extra={"task_id": task_id, "reminder_id": reminder_id, "result": retval}
        )
        super().on_success(retval, task_id, args, kwargs)


@celery_app.task(
    base=ReminderTask,
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    queue="high_priority",
    time_limit=60,
    soft_time_limit=45,
)
def send_reminder_task(self, reminder_id: int) -> dict:
    """
    Send a reminder notification with resilient retry and monitoring.
    
    Args:
        reminder_id: The ID of the reminder to send
        
    Returns:
        dict with status and delivery information
        
    Raises:
        self.retry: On recoverable failures, with exponential backoff
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        # Fetch reminder from database
        reminder = Reminder.query.get(reminder_id)
        if not reminder:
            logger.warning(f"Reminder {reminder_id} not found")
            return {"status": "error", "reason": "reminder_not_found"}
        
        # Check if already sent (idempotency)
        cache_key = f"reminder:sent:{reminder_id}"
        if redis_client.get(cache_key):
            logger.info(f"Reminder {reminder_id} already sent, skipping")
            return {"status": "skipped", "reason": "already_sent"}
        
        # Determine channel and send
        channel = reminder.channel
        success = False
        
        if channel.startswith("whatsapp:"):
            to_number = channel.split(":", 1)[1]
            success = send_whatsapp(to_number, reminder.message)
            channel_type = "whatsapp"
        elif "@" in channel:
            success = send_email(channel, "Bill Reminder", reminder.message)
            channel_type = "email"
        else:
            logger.warning(f"Unknown channel type for reminder {reminder_id}: {channel}")
            return {"status": "error", "reason": "unknown_channel"}
        
        # Record delivery attempt
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        log_entry = NotificationLog(
            reminder_id=reminder_id,
            channel=channel_type,
            status="delivered" if success else "failed",
            sent_at=start_time,
            duration_ms=int(duration_ms),
            retry_count=self.request.retries,
        )
        db.session.add(log_entry)
        
        if success:
            # Mark as sent in cache (24 hour TTL)
            redis_client.setex(cache_key, 86400, "1")
            reminder.is_sent = True
            reminder.sent_at = start_time
            db.session.commit()
            
            track_reminder_event("send", channel_type, "ok")
            logger.info(f"Reminder {reminder_id} sent successfully via {channel_type}")
            
            return {
                "status": "success",
                "channel": channel_type,
                "duration_ms": duration_ms,
                "reminder_id": reminder_id,
            }
        else:
            db.session.commit()
            track_reminder_event("send", channel_type, "failed")
            
            # Determine if retryable
            if self.request.retries < self.max_retries:
                countdown = min(2 ** self.request.retries * 60, 3600)  # Max 1 hour
                logger.warning(
                    f"Reminder {reminder_id} delivery failed, retrying in {countdown}s "
                    f"(attempt {self.request.retries + 1}/{self.max_retries})"
                )
                raise self.retry(countdown=countdown)
            else:
                logger.error(f"Reminder {reminder_id} failed after max retries")
                # Send to dead letter queue for manual inspection
                _send_to_dead_letter(reminder_id, "max_retries_exceeded", self.request.id)
                return {"status": "failed", "reason": "max_retries_exceeded"}
                
    except SoftTimeLimitExceeded:
        logger.error(f"Reminder {reminder_id} task timed out")
        db.session.rollback()
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=120)
        _send_to_dead_letter(reminder_id, "timeout", self.request.id)
        return {"status": "failed", "reason": "timeout"}
        
    except Exception as exc:
        logger.exception(f"Unexpected error sending reminder {reminder_id}")
        db.session.rollback()
        
        if self.request.retries < self.max_retries:
            countdown = min(2 ** self.request.retries * 60, 3600)
            raise self.retry(exc=exc, countdown=countdown)
        else:
            _send_to_dead_letter(reminder_id, str(exc), self.request.id)
            raise


def _send_to_dead_letter(reminder_id: int, reason: str, task_id: Optional[str] = None):
    """
    Send failed task to dead letter queue for manual inspection.
    
    Args:
        reminder_id: The failed reminder ID
        reason: Failure reason
        task_id: Original Celery task ID
    """
    import json
    dead_letter_key = f"dead_letter:reminders:{reminder_id}"
    dead_letter_data = {
        "reminder_id": reminder_id,
        "reason": reason,
        "original_task_id": task_id,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.setex(dead_letter_key, 604800, json.dumps(dead_letter_data))
    logger.warning(f"Reminder {reminder_id} sent to dead letter queue: {reason}")


@celery_app.task(queue="low_priority")
def cleanup_old_reminders(days: int = 30) -> dict:
    """
    Cleanup old sent reminders to maintain database performance.
    
    Args:
        days: Age in days of reminders to cleanup
        
    Returns:
        dict with cleanup statistics
    """
    from datetime import timedelta
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    old_logs = NotificationLog.query.filter(
        NotificationLog.sent_at < cutoff_date
    ).delete()
    
    db.session.commit()
    
    logger.info(f"Cleaned up {old_logs} old notification logs")
    return {"deleted_count": old_logs, "cutoff_date": cutoff_date.isoformat()}


@celery_app.task(queue="high_priority")
def process_due_reminders() -> dict:
    """
    Process all reminders that are due to be sent.
    Called periodically by Celery beat.
    
    Returns:
        dict with processing statistics
    """
    now = datetime.now(timezone.utc)
    
    # Find reminders that are due and not yet sent
    due_reminders = Reminder.query.filter(
        Reminder.send_at <= now,
        Reminder.is_sent == False
    ).all()
    
    scheduled = 0
    errors = 0
    
    for reminder in due_reminders:
        try:
            # Schedule with stagger to avoid thundering herd
            send_reminder_task.apply_async(
                args=[reminder.id],
                countdown=scheduled * 5  # 5 second stagger
            )
            scheduled += 1
        except Exception as exc:
            logger.error(f"Failed to schedule reminder {reminder.id}: {exc}")
            errors += 1
    
    logger.info(f"Scheduled {scheduled} due reminders ({errors} errors)")
    return {
        "scheduled": scheduled,
        "errors": errors,
        "total_due": len(due_reminders),
        "processed_at": now.isoformat(),
    }
