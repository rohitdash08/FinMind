import smtplib
import time
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional, Tuple
from ..config import Settings
from ..models import Reminder, ReminderDelivery
from ..extensions import db

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


_settings = Settings()

# Delivery retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_MINUTES = [5, 15, 60]  # Exponential backoff delays


def send_email(to_email: str, subject: str, body: str) -> Tuple[bool, Optional[str]]:
    """Send email and return (success, error_message)."""
    if not _settings.smtp_url or not _settings.email_from:
        return False, "SMTP not configured"
    try:
        # Very light SMTP URL parser: smtp+ssl://user:pass@host:465
        import re

        m = re.match(r"smtp\+ssl://(.+?):(.+?)@(.+?):(\d+)", _settings.smtp_url)
        if not m:
            return False, "Invalid SMTP URL format"
        user, pwd, host, port = m.groups()
        msg = EmailMessage()
        msg["From"] = _settings.email_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(host, int(port)) as s:
            s.login(user, pwd)
            s.send_message(msg)
        return True, None
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def send_whatsapp(to_number: str, body: str) -> Tuple[bool, Optional[str]]:
    """Send WhatsApp message and return (success, error_message)."""
    if not (
        _settings.twilio_account_sid
        and _settings.twilio_auth_token
        and _settings.twilio_whatsapp_from
        and TwilioClient
    ):
        return False, "Twilio not configured"
    try:
        client = TwilioClient(_settings.twilio_account_sid, _settings.twilio_auth_token)
        client.messages.create(
            body=body,
            from_=_settings.twilio_whatsapp_from,
            to=to_number,
        )
        return True, None
    except Exception as e:
        return False, str(e)


def send_reminder(r: Reminder) -> Tuple[bool, Optional[str], int]:
    """
    Send a reminder and track delivery.
    Returns: (success, error_message, response_time_ms)
    """
    start_time = time.time()
    
    # Channel holds 'email' or 'whatsapp:<number>'
    if r.channel == "whatsapp":
        return False
    if r.channel.startswith("whatsapp:"):
        to = r.channel.split(":", 1)[1]
        success, error = send_whatsapp(to, r.message)
    else:
        # Fallback: assume email stored in channel as email
        to = r.channel if "@" in r.channel else (_settings.email_from or "")
        subject = "Bill Reminder"
        success, error = send_email(to, subject, r.message)
    
    response_time_ms = int((time.time() - start_time) * 1000)
    return success, error, response_time_ms


def deliver_reminder(r: Reminder) -> bool:
    """
    Deliver a reminder with tracking and retry logic.
    Returns True if delivered successfully (or max retries reached).
    """
    success, error, response_time_ms = send_reminder(r)
    
    # Update reminder tracking
    r.delivery_attempts += 1
    r.last_attempt_at = datetime.utcnow()
    
    # Record delivery attempt
    delivery = ReminderDelivery(
        reminder_id=r.id,
        success=success,
        channel=r.channel,
        error_message=error,
        response_time_ms=response_time_ms,
    )
    db.session.add(delivery)
    
    if success:
        r.sent = True
        r.delivered = True
        r.error_message = None
    else:
        r.delivered = False
        r.error_message = error
        
        # Schedule retry if under max attempts
        if r.delivery_attempts < MAX_RETRY_ATTEMPTS:
            delay_minutes = RETRY_DELAY_MINUTES[min(r.delivery_attempts - 1, len(RETRY_DELAY_MINUTES) - 1)]
            r.send_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        else:
            # Max retries reached, mark as failed
            r.sent = True  # Mark as processed even if failed
    
    db.session.commit()
    return success


def get_delivery_metrics(user_id: int, days: int = 30) -> dict:
    """Get delivery reliability metrics for a user."""
    from_date = datetime.utcnow() - timedelta(days=days)
    
    # Get all deliveries for user's reminders in the time period
    deliveries = (
        db.session.query(ReminderDelivery)
        .join(Reminder)
        .filter(
            Reminder.user_id == user_id,
            ReminderDelivery.attempted_at >= from_date,
        )
        .all()
    )
    
    if not deliveries:
        return {
            "period_days": days,
            "total_attempts": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "success_rate": 0.0,
            "average_response_time_ms": 0,
        }
    
    total = len(deliveries)
    successful = sum(1 for d in deliveries if d.success)
    failed = total - successful
    success_rate = (successful / total * 100) if total > 0 else 0.0
    
    response_times = [d.response_time_ms for d in deliveries if d.response_time_ms is not None]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    # Channel breakdown
    email_attempts = [d for d in deliveries if d.channel == "email"]
    whatsapp_attempts = [d for d in deliveries if d.channel.startswith("whatsapp")]
    
    return {
        "period_days": days,
        "total_attempts": total,
        "successful_deliveries": successful,
        "failed_deliveries": failed,
        "success_rate": round(success_rate, 2),
        "average_response_time_ms": round(avg_response_time, 2),
        "by_channel": {
            "email": {
                "attempts": len(email_attempts),
                "successful": sum(1 for d in email_attempts if d.success),
                "success_rate": round(sum(1 for d in email_attempts if d.success) / len(email_attempts) * 100, 2) if email_attempts else 0,
            },
            "whatsapp": {
                "attempts": len(whatsapp_attempts),
                "successful": sum(1 for d in whatsapp_attempts if d.success),
                "success_rate": round(sum(1 for d in whatsapp_attempts if d.success) / len(whatsapp_attempts) * 100, 2) if whatsapp_attempts else 0,
            },
        },
    }


def get_failed_reminders(user_id: int, limit: int = 10) -> list:
    """Get recent failed reminders that need attention."""
    reminders = (
        db.session.query(Reminder)
        .filter(
            Reminder.user_id == user_id,
            Reminder.delivered == False,
            Reminder.delivery_attempts >= MAX_RETRY_ATTEMPTS,
        )
        .order_by(Reminder.last_attempt_at.desc())
        .limit(limit)
        .all()
    )
    return reminders
