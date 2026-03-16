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


def send_reminder(r: Reminder) -> bool:
    # Channel holds 'email' or 'whatsapp:<number>'
    if r.channel == "whatsapp":
        raise RuntimeError("whatsapp channel requires 'whatsapp:<number>' format")
    if r.channel.startswith("whatsapp:"):
        to = r.channel.split(":", 1)[1]
        result = send_whatsapp(to, r.message)
        if not result:
            raise RuntimeError(f"WhatsApp delivery failed for {to}")
        return True
    else:
        to = r.channel if "@" in r.channel else (_settings.email_from or "")
        if not to:
            raise RuntimeError("No email address configured for reminder delivery")
        result = send_email(to, "Bill Reminder", r.message)
        if not result:
            raise RuntimeError(f"Email delivery failed for {to}")
        return True
