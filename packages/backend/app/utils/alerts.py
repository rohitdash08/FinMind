import logging
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)

def send_alert_email(user_email: str, ip_address: str, user_agent: str, login_time: datetime):
    """
    Simulates sending an alert email for suspicious login activity.
    In a production environment, this would integrate with an actual email service
    (e.g., Flask-Mail, SendGrid, Mailgun) and likely use a background task queue
    (e.g., Celery) to avoid blocking the request.
    """
    with current_app.app_context():
        subject = "Suspicious Login Alert for Your FinMind Account"
        body = (
            f"Dear FinMind User,\n\n"
            f"We detected a login to your account ({user_email}) from a new or "
            f"unrecognized device/location.\n\n"
            f"Details:\n"
            f"  IP Address: {ip_address}\n"
            f"  User Agent: {user_agent}\n"
            f"  Time: {login_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"If this was you, you can safely ignore this email.\n"
            f"If this was NOT you, please change your password immediately and contact support.\n\n"
            f"Regards,\n"
            f"The FinMind Team"
        )
        logger.warning(
            f"ALERT: Sending suspicious login email to {user_email}. "
            f"IP: {ip_address}, User-Agent: '{user_agent}', Time: {login_time}"
        )
        # Placeholder for actual email sending logic:
        # from flask_mail import Message, Mail
        # mail = Mail(current_app)
        # msg = Message(subject, recipients=[user_email], body=body)
        # mail.send(msg)

