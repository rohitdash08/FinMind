import logging
from datetime import datetime, timedelta

from ..extensions import db
from ..models import LoginAnomaly, LoginEvent, User
from .reminders import send_email

logger = logging.getLogger("finmind.login_anomaly")

# Thresholds
BRUTE_FORCE_WINDOW_MINUTES = 15
BRUTE_FORCE_MAX_FAILURES = 5
ODD_HOUR_START = 2  # UTC
ODD_HOUR_END = 5  # UTC


def record_login_event(
    user_id: int, ip_address: str, user_agent: str | None, success: bool
) -> LoginEvent:
    event = LoginEvent(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
    )
    db.session.add(event)
    db.session.flush()
    return event


def detect_anomalies(event: LoginEvent) -> list[LoginAnomaly]:
    anomalies: list[LoginAnomaly] = []

    if event.success:
        if _is_new_ip(event):
            anomalies.append(
                _create_anomaly(
                    event,
                    "NEW_IP",
                    f"Login from new IP address: {event.ip_address}",
                )
            )
        if _is_new_device(event):
            agent_short = (event.user_agent or "unknown")[:100]
            anomalies.append(
                _create_anomaly(
                    event,
                    "NEW_DEVICE",
                    f"Login from new device: {agent_short}",
                )
            )
        if _is_odd_hour(event):
            hour = event.created_at.hour
            anomalies.append(
                _create_anomaly(
                    event,
                    "ODD_HOUR",
                    f"Login at unusual hour: {hour:02d}:00 UTC",
                )
            )

    if _is_brute_force(event):
        anomalies.append(
            _create_anomaly(
                event,
                "BRUTE_FORCE",
                f"Multiple failed login attempts from IP {event.ip_address}",
            )
        )

    return anomalies


def send_anomaly_alerts(user: User, anomalies: list[LoginAnomaly]) -> None:
    if not anomalies:
        return
    descriptions = "\n".join(f"  - {a.detail}" for a in anomalies)
    subject = "FinMind Security Alert: Suspicious Login Activity"
    body = (
        f"Hello,\n\n"
        f"We detected unusual activity on your FinMind account:\n\n"
        f"{descriptions}\n\n"
        f"If this was you, you can acknowledge these alerts in the app.\n"
        f"If not, please change your password immediately.\n\n"
        f"— FinMind Security"
    )
    sent = send_email(user.email, subject, body)
    if sent:
        logger.info("Anomaly alert email sent to user_id=%s", user.id)
    else:
        logger.info(
            "Anomaly alert email skipped (SMTP not configured) user_id=%s",
            user.id,
        )


def _is_new_ip(event: LoginEvent) -> bool:
    previous = (
        db.session.query(LoginEvent.id)
        .filter(
            LoginEvent.user_id == event.user_id,
            LoginEvent.ip_address == event.ip_address,
            LoginEvent.success.is_(True),
            LoginEvent.id != event.id,
        )
        .first()
    )
    return previous is None


def _is_new_device(event: LoginEvent) -> bool:
    if not event.user_agent:
        return False
    previous = (
        db.session.query(LoginEvent.id)
        .filter(
            LoginEvent.user_id == event.user_id,
            LoginEvent.user_agent == event.user_agent,
            LoginEvent.success.is_(True),
            LoginEvent.id != event.id,
        )
        .first()
    )
    return previous is None


def _is_brute_force(event: LoginEvent) -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES)
    fail_count = (
        db.session.query(db.func.count(LoginEvent.id))
        .filter(
            LoginEvent.user_id == event.user_id,
            LoginEvent.success.is_(False),
            LoginEvent.created_at >= cutoff,
        )
        .scalar()
    )
    return fail_count >= BRUTE_FORCE_MAX_FAILURES


def _is_odd_hour(event: LoginEvent) -> bool:
    hour = event.created_at.hour
    return ODD_HOUR_START <= hour < ODD_HOUR_END


def _create_anomaly(event: LoginEvent, anomaly_type: str, detail: str) -> LoginAnomaly:
    anomaly = LoginAnomaly(
        user_id=event.user_id,
        login_event_id=event.id,
        anomaly_type=anomaly_type,
        detail=detail,
    )
    db.session.add(anomaly)
    logger.info(
        "Anomaly detected type=%s user_id=%s detail=%s",
        anomaly_type,
        event.user_id,
        detail,
    )
    return anomaly
