import smtplib
from email.message import EmailMessage
from ..config import Settings
from ..models import Reminder

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


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
    # Channel holds 'email' or 'whatsapp:<number>'
    if r.channel == "whatsapp":
        return False
    if r.channel.startswith("whatsapp:"):
        to = r.channel.split(":", 1)[1]
        return send_whatsapp(to, r.message)
    else:
        # Fallback: assume email stored in channel as email
        # or pull from user profile later
        to = r.channel if "@" in r.channel else (_settings.email_from or "")
        subject = "Bill Reminder"
        return send_email(to, subject, r.message)


def send_reminder_with_job(r: Reminder):
    """Wrap send_reminder with job enqueueing for retry support."""
    from .jobs import enqueue_job, register_handler

    if r.channel.startswith("whatsapp:"):
        job_type = "reminder_whatsapp"
    else:
        job_type = "reminder_email"

    payload = {
        "reminder_id": r.id,
        "channel": r.channel,
        "message": r.message,
    }
    return enqueue_job(job_type, payload=payload, user_id=r.user_id)


def _handle_reminder_email(payload: dict) -> bool:
    to = payload.get("channel", "")
    if "@" not in to:
        to = _settings.email_from or ""
    subject = "Bill Reminder"
    result = send_email(to, subject, payload["message"])
    if not result:
        raise RuntimeError("send_email failed")
    return True


def _handle_reminder_whatsapp(payload: dict) -> bool:
    channel = payload.get("channel", "")
    if channel.startswith("whatsapp:"):
        to = channel.split(":", 1)[1]
    else:
        raise RuntimeError("Invalid whatsapp channel format")
    result = send_whatsapp(to, payload["message"])
    if not result:
        raise RuntimeError("send_whatsapp failed")
    return True


def register_reminder_handlers():
    """Register reminder job handlers with the job system."""
    from .jobs import register_handler
    register_handler("reminder_email", _handle_reminder_email)
    register_handler("reminder_whatsapp", _handle_reminder_whatsapp)
