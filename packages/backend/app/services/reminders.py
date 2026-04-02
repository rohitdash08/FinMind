import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from ..config import Settings
from ..models import Reminder

from ..extensions import db

from ..observability import track_reminder_event

import logging

logger = logging.getLogger("finmind.reminders")

_settings = Settings()
MAX_RETRIES = 5
BASE_RETRY_DELAY_MINUTES = 5


try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


def send_email(to_email: str, subject: str, body: str):
    if not _settings.smtp_url or not _settings.email_from:
        return False
    try:
        import re

        m = re.match(r"smtp\+ssl://(.+?):(.+?)@(.+?):(\d+)", _settings.smtp_url)
        if not m:
            return False
        user, pwd, host, port = m.groups()
        msg = EmailMessage()
        msg["From"] = _settings.email_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(host, int(port)) as s:
            s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception as e:
        logger.error("SMTP error: %s", e)
        return False


def send_whatsapp(to_number: str, body: str):
    if not (
        _settings.twilio_account_sid
        and _settings.twilio_auth_token
        and _settings.twilio_whatsapp_from
        and TwilioClient
    ):
        return False
    try:
        client = TwilioClient(_settings.twilio_account_sid, _settings.twilio_auth_token)
        client.messages.create(
            body=body,
            from_=_settings.twilio_whatsapp_from,
            to=to_number,
        )
        return True
    except Exception as e:
        logger.error("Twilio error: %s", e)
        return False


def _send_reminder_internal(r: Reminder) -> bool:
    """Low-level send. Returns True on success, False on failure."""
    # Channel holds 'email' or 'whatsapp:<number>'
    if r.channel == "whatsapp":
        return False
    if r.channel.startswith("whatsapp:"):
        to = r.channel.split(":", 1)[1]
        return send_whatsapp(to, r.message)
    else:
        to = r.channel if "@" in r.channel else (_settings.email_from or "")
        subject = "Bill Reminder"
        return send_email(to, subject, r.message)


def dispatch_reminder(reminder_id: int) -> None:
    """
    Process a single reminder with retry logic and exponential backoff.

    - If reminder is already sent, skip.
    - If status is 'failed' and retry_count >= MAX_RETRIES, skip.
    - If next_retry_at is in the future, skip (not time yet).
    - Attempt to send. On success: mark sent, clear retry fields, set status='sent'.
    - On failure: increment retry_count, set last_retry_at, compute next_retry_at,
      set failure_reason, set status='retrying' or 'failed' if max retries reached.
    """
    with db.session.begin():
        r = db.session.get(Reminder, reminder_id)
        if not r:
            logger.warning("dispatch_reminder: reminder %s not found", reminder_id)
            return

        now = datetime.utcnow()

        # Skip if already sent
        if r.sent:
            logger.debug("dispatch_reminder: reminder %s already sent", reminder_id)
            return

        # Skip if max retries exceeded and status is failed
        if r.status == "failed" and r.retry_count >= MAX_RETRIES:
            logger.warning(
                "dispatch_reminder: reminder %s permanently failed after %s retries",
                reminder_id,
                r.retry_count,
            )
            return

        # Skip if next_retry_at is in the future
        if r.next_retry_at and r.next_retry_at > now:
            logger.debug(
                "dispatch_reminder: reminder %s not ready until %s",
                reminder_id,
                r.next_retry_at,
            )
            return

        # Attempt to send
        success = _send_reminder_internal(r)
        if success:
            r.sent = True
            r.status = "sent"
            r.retry_count = 0
            r.last_retry_at = None
            r.next_retry_at = None
            r.failure_reason = None
            logger.info("dispatch_reminder: reminder %s sent successfully", reminder_id)
            db.session.commit()
            track_reminder_event(event="sent", channel=r.channel)
            return

        # Failure handling
        r.retry_count += 1
        r.last_retry_at = now
        r.failure_reason = "send_reminder failed"

        if r.retry_count >= MAX_RETRIES:
            r.status = "failed"
            r.next_retry_at = None
            logger.error(
                "dispatch_reminder: reminder %s failed after %s retries",
                reminder_id,
                r.retry_count,
            )
            track_reminder_event(event="failed", channel=r.channel, status="max_retries")
        else:
            # Calculate exponential backoff: base * (2 ^ (retry_count - 1))
            delay_minutes = BASE_RETRY_DELAY_MINUTES * (2 ** (r.retry_count - 1))
            r.next_retry_at = now + timedelta(minutes=delay_minutes)
            r.status = "retrying"
            logger.info(
                "dispatch_reminder: reminder %s failed, scheduling retry %s at %s",
                reminder_id,
                r.retry_count,
                r.next_retry_at,
            )
            track_reminder_event(event="retry", channel=r.channel, status=str(r.retry_count))

        db.session.commit()
