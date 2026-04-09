from flask import current_app
from datetime import datetime, timedelta
import pytz

def detect_suspicious_login(user, current_ip, current_user_agent) -> bool:
    """
    Detects if a login attempt is suspicious based on last successful login.
    A login is considered suspicious if:
    1. The IP address is different from the last successful login IP AND
    2. The User-Agent string is different from the last successful login User-Agent.

    This simple heuristic aims to reduce false positives from common scenarios
    like changing mobile network IP (but keeping same device/browser) or
    browser updates (but keeping same IP).
    """
    if not user or not user.last_login_at or not user.last_login_ip or not user.last_login_user_agent:
        # First login or no previous successful login data to compare against
        return False

    is_ip_different = user.last_login_ip != current_ip
    is_ua_different = user.last_login_user_agent != current_user_agent

    # Consider suspicious if both IP and User-Agent have changed
    if is_ip_different and is_ua_different:
        current_app.logger.warning(
            f"Suspicious login detected for user {user.email}: "
            f"IP changed from {user.last_login_ip} to {current_ip}, "
            f"UA changed from '{user.last_login_user_agent}' to '{current_user_agent}'"
        )
        return True

    return False

def send_suspicious_activity_email(user, login_attempt):
    """
    Sends an email notification about a suspicious login attempt.
    In a real application, this would integrate with an email sending service.
    """
    from app.utils.email import send_email # Deferred import

    current_app.logger.warning(
        f"ALERT: Attempting to send suspicious login email to {user.email} "
        f"for login from IP {login_attempt.ip_address} on {login_attempt.timestamp} UTC."
    )
    
    # Example email content (would typically be rendered from a template)
    subject = "Security Alert: Unusual Login Activity Detected!"
    body = (
        f"Dear {user.email},\n\n"
        "We detected an unusual login to your FinMind account.\n"
        f"Details:\n"
        f"Time: {login_attempt.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} UTC\n"
        f"IP Address: {login_attempt.ip_address}\n"
        f"User Agent: {login_attempt.user_agent}\n\n"
        "If this was you, you can safely ignore this alert.\n"
        "If this was not you, please change your password immediately and review your account activity.\n\n"
        "Thank you,\n"
        "The FinMind Team"
    )
    send_email(user.email, subject, body)

