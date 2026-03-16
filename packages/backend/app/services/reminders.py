import smtplib
from email.message import EmailMessage
from ..config import Settings
from ..models import Reminder, User

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


def send_reminder(r: Reminder) -> None:
    # Channel holds 'email' or 'whatsapp:<number>'
    if r.channel == "whatsapp":
        raise RuntimeError("whatsapp channel requires 'whatsapp:<number>' format")
    if r.channel.startswith("whatsapp:"):
        to = r.channel.split(":", 1)[1]
        if not send_whatsapp(to, r.message):
            raise RuntimeError(f"WhatsApp delivery failed for {to}")
        return
    # Email: use r.channel if it's an email address, otherwise look up User.email
    if "@" in r.channel:
        to = r.channel
    else:
        user = User.query.get(r.user_id)
        to = user.email if user else None
    if not to:
        raise RuntimeError(f"No email address available for reminder id={r.id}")
    if not send_email(to, "Bill Reminder", r.message):
        raise RuntimeError(f"Email delivery failed for {to}")
