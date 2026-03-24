import smtplib
import logging
from email.message import EmailMessage
from ..config import Settings
from ..models import Reminder
from .jobs import register_handler

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


logger = logging.getLogger("finmind.reminders.service")
_settings = Settings()


def send_email(to_email: str, subject: str, body: str):
    if not _settings.smtp_url or not _settings.email_from:
        return False
    try:
        # Very light SMTP URL parser: smtp+ssl://user:pass@host:465
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
    except Exception:
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
    except Exception:
        return False


def send_reminder(r: Reminder):
    """Send a reminder via the configured channel.

    Returns True on success, False on failure (legacy interface).
    Raises RuntimeError on failure when called from the job system.
    """
    # Channel holds 'email' or 'whatsapp:<number>'
    if r.channel == "whatsapp":
        return False
    if r.channel.startswith("whatsapp:"):
        to = r.channel.split(":", 1)[1]
        success = send_whatsapp(to, r.message)
        if not success:
            raise RuntimeError(f"WhatsApp send failed to {to}")
        return True
    else:
        # Fallback: assume email stored in channel as email
        # or pull from user profile later
        to = r.channel if "@" in r.channel else (_settings.email_from or "")
        subject = "Bill Reminder"
        success = send_email(to, subject, r.message)
        if not success:
            raise RuntimeError(f"Email send failed to {to}")
        return True


# ---------------------------------------------------------------------------
# Job handler: integrates send_reminder with the resilient job system
# ---------------------------------------------------------------------------


@register_handler("send_reminder")
def handle_send_reminder_job(payload: dict) -> dict:
    """Job handler for sending a reminder.

    Expected payload: {"reminder_id": int}
    Fetches the Reminder from DB, sends it, and marks it as sent.
    Raises on failure so the job system can retry.
    """
    from ..extensions import db

    reminder_id = payload.get("reminder_id")
    if not reminder_id:
        raise ValueError("Missing reminder_id in job payload")

    reminder = db.session.get(Reminder, reminder_id)
    if not reminder:
        raise ValueError(f"Reminder {reminder_id} not found")

    if reminder.sent:
        logger.info("Reminder %s already sent, skipping", reminder_id)
        return {"status": "already_sent", "reminder_id": reminder_id}

    send_reminder(reminder)
    reminder.sent = True
    db.session.commit()
    logger.info("Reminder %s sent successfully via %s", reminder_id, reminder.channel)
    return {"status": "sent", "reminder_id": reminder_id, "channel": reminder.channel}
