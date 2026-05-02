from __future__ import annotations

from datetime import datetime, timedelta

from ..extensions import db
from ..models import LoginEvent, SecurityAlert, User

FAILED_LOGIN_THRESHOLD = 5
FAILED_LOGIN_WINDOW_MINUTES = 15


def client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def user_agent(request) -> str:
    return (request.headers.get("User-Agent") or "unknown")[:500]


def record_failed_login(email: str | None, ip_address: str, agent: str) -> None:
    normalized_email = (email or "").strip().lower() or "unknown"
    event = LoginEvent(
        email=normalized_email,
        ip_address=ip_address,
        user_agent=agent,
        success=False,
    )
    db.session.add(event)
    db.session.commit()


def record_successful_login(user: User, ip_address: str, agent: str) -> list[SecurityAlert]:
    email = (user.email or "").strip().lower()
    previous_successes = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == user.id, LoginEvent.success.is_(True))
        .all()
    )

    known_ips = {item.ip_address for item in previous_successes if item.ip_address}
    known_agents = {item.user_agent for item in previous_successes if item.user_agent}
    alerts: list[SecurityAlert] = []

    if previous_successes and ip_address not in known_ips:
        alerts.append(
            _build_alert(
                user.id,
                "new_ip",
                "medium",
                "New sign-in location detected for your account.",
                ip_address,
                agent,
            )
        )
    if previous_successes and agent not in known_agents:
        alerts.append(
            _build_alert(
                user.id,
                "new_device",
                "medium",
                "New device or browser detected for your account.",
                ip_address,
                agent,
            )
        )

    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_LOGIN_WINDOW_MINUTES)
    failures = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.email == email,
            LoginEvent.success.is_(False),
            LoginEvent.created_at >= cutoff,
        )
        .count()
    )
    if failures >= FAILED_LOGIN_THRESHOLD:
        alerts.append(
            _build_alert(
                user.id,
                "failed_login_burst",
                "high",
                f"{failures} failed login attempts were detected in the last {FAILED_LOGIN_WINDOW_MINUTES} minutes.",
                ip_address,
                agent,
            )
        )

    db.session.add(
        LoginEvent(
            user_id=user.id,
            email=email,
            ip_address=ip_address,
            user_agent=agent,
            success=True,
        )
    )
    for alert in alerts:
        db.session.add(alert)
    db.session.commit()
    return alerts


def serialize_alert(alert: SecurityAlert) -> dict:
    return {
        "id": alert.id,
        "type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "ip_address": alert.ip_address,
        "user_agent": alert.user_agent,
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat() + "Z",
    }


def _build_alert(user_id: int, alert_type: str, severity: str, message: str, ip_address: str, agent: str) -> SecurityAlert:
    return SecurityAlert(
        user_id=user_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        ip_address=ip_address,
        user_agent=agent,
    )
