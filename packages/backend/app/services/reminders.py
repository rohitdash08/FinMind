import smtplib
import logging
from email.message import EmailMessage
from ..config import Settings
from ..models import Reminder

try:
    import resend as resend_sdk
except Exception:  # pragma: no cover
    resend_sdk = None  # type: ignore[assignment]

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


_settings = Settings()
logger = logging.getLogger("finmind.reminders")


def _send_via_resend(to_email: str, subject: str, body: str) -> bool:
    """Send email using Resend SDK (recommended)."""
    if not resend_sdk or not _settings.resend_api_key:
        return False
    try:
        resend_sdk.api_key = _settings.resend_api_key
        params: dict = {
            "from": _settings.email_from or "FinMind <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        result = resend_sdk.Emails.send(params)
        logger.info("Email sent via Resend to=%s id=%s", to_email, result.get("id"))
        return True
    except Exception:
        logger.exception("Resend send failed to=%s", to_email)
        return False


def _send_via_smtp(to_email: str, subject: str, body: str) -> bool:
    """Send email using SMTP (fallback)."""
    if not _settings.smtp_url or not _settings.email_from:
        return False
    try:
        import re

        m = re.match(r"smtp\+ssl://(.+?):(.+?)@(.+?):(\d+)", _settings.smtp_url)
        if not m:
            logger.error("Email not sent: invalid SMTP_URL format")
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
        logger.info("Email sent via SMTP to=%s subject=%s", to_email, subject)
        return True
    except Exception:
        logger.exception("SMTP send failed to=%s", to_email)
        return False


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send email using Resend SDK (primary) or SMTP (fallback).

    Priority: Resend API key > SMTP URL > skip.
    """
    if _settings.resend_api_key:
        return _send_via_resend(to_email, subject, body)

    if _settings.smtp_url:
        return _send_via_smtp(to_email, subject, body)

    logger.warning("Email not sent: neither RESEND_API_KEY nor SMTP_URL configured")
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
