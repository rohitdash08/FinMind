import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Callable
from ..config import Settings
from ..models import Reminder

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


_settings = Settings()
DEFAULT_RETRY_DELAYS = (
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=45),
)
MAX_REMINDER_RETRIES = len(DEFAULT_RETRY_DELAYS)


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


def dispatch_reminder(
    reminder: Reminder,
    *,
    now: datetime | None = None,
    sender: Callable[[Reminder], bool] = send_reminder,
) -> str:
    """Attempt one reminder delivery and persist retry/dead-letter fields."""
    attempted_at = now or datetime.utcnow()
    reminder.last_attempt_at = attempted_at

    try:
        delivered = bool(sender(reminder))
    except Exception as exc:  # pragma: no cover - tested through raised subclass
        delivered = False
        reminder.last_error = str(exc)[:1000]
    else:
        if not delivered:
            reminder.last_error = "Reminder delivery returned false"

    if delivered:
        reminder.sent = True
        reminder.sent_at = attempted_at
        reminder.failed = False
        reminder.next_retry_at = None
        reminder.last_error = None
        return "sent"

    reminder.retry_count = (reminder.retry_count or 0) + 1
    if reminder.retry_count >= MAX_REMINDER_RETRIES:
        reminder.failed = True
        reminder.next_retry_at = None
        return "failed"

    reminder.next_retry_at = (
        attempted_at + DEFAULT_RETRY_DELAYS[reminder.retry_count - 1]
    )
    return "retrying"


def reset_failed_reminder(
    reminder: Reminder, *, send_at: datetime | None = None
) -> None:
    reminder.failed = False
    reminder.sent = False
    reminder.retry_count = 0
    reminder.next_retry_at = None
    reminder.last_attempt_at = None
    reminder.sent_at = None
    reminder.last_error = None
    if send_at is not None:
        reminder.send_at = send_at
