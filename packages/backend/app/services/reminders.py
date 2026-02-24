import smtplib
from email.message import EmailMessage
from ..config import Settings
from ..models import Reminder, ReminderDeliveryLog

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


def _do_send(r: Reminder) -> bool:
    """Core send logic — email or whatsapp dispatch (no logging here)."""
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


def send_reminder(r: Reminder) -> bool:
    """Send a reminder and log the delivery attempt to ReminderDeliveryLog."""
    from datetime import datetime as _dt

    attempt_time = _dt.utcnow()
    success = False
    error_msg = None
    try:
        success = _do_send(r)
    except Exception as exc:
        error_msg = str(exc)[:500]
        success = False
    finally:
        try:
            from ..extensions import db as _db

            latency = None
            if hasattr(r, "send_at") and r.send_at:
                delta = attempt_time - r.send_at
                latency = int(delta.total_seconds())
            log = ReminderDeliveryLog(
                reminder_id=r.id,
                channel=r.channel or "email",
                attempted_at=attempt_time,
                success=success,
                error_message=error_msg,
                latency_seconds=latency,
            )
            _db.session.add(log)
            _db.session.commit()
        except Exception:
            pass  # never let logging break the scheduler
    return success
