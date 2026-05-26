import json
from datetime import UTC, datetime, timedelta
from flask import request
from ..extensions import db
from ..models import LoginEvent, SecurityAlert, User


FAILED_LOGIN_WINDOW = timedelta(minutes=15)
FAILED_LOGIN_THRESHOLD = 5


ALERT_MESSAGES = {
    "new_ip": "New login location detected.",
    "new_device": "New device or browser detected.",
    "unusual_hour": "Login happened at an unusual hour.",
    "failed_login_burst": (
        "Multiple failed login attempts were detected before this login."
    ),
}


def request_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return (request.remote_addr or "unknown").strip() or "unknown"


def request_user_agent() -> str:
    return (request.headers.get("User-Agent") or "unknown").strip()[:500] or "unknown"


def record_failed_login(user: User | None, email: str) -> None:
    if not user:
        return
    event = LoginEvent(
        user_id=user.id,
        email=email or user.email,
        ip_address=request_ip(),
        user_agent=request_user_agent(),
        success=False,
        failure_reason="invalid_credentials",
    )
    db.session.add(event)
    db.session.commit()


def record_successful_login(user: User) -> list[SecurityAlert]:
    now = datetime.now(UTC).replace(tzinfo=None)
    ip_address = request_ip()
    user_agent = request_user_agent()
    event = LoginEvent(
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        occurred_at=now,
    )
    db.session.add(event)
    db.session.flush()

    reasons = _detect_reasons(user.id, event.id, ip_address, user_agent, now)
    alerts = [
        _make_alert(user.id, event.id, reason, ip_address, user_agent)
        for reason in reasons
    ]
    if reasons:
        event.is_suspicious = True
        event.suspicion_reasons = json.dumps(reasons)
        db.session.add_all(alerts)

    db.session.commit()
    return alerts


def serialize_login_event(event: LoginEvent) -> dict:
    return {
        "id": event.id,
        "email": event.email,
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "success": event.success,
        "failure_reason": event.failure_reason,
        "is_suspicious": event.is_suspicious,
        "suspicion_reasons": _loads(event.suspicion_reasons, []),
        "occurred_at": event.occurred_at.isoformat(),
    }


def serialize_security_alert(alert: SecurityAlert) -> dict:
    return {
        "id": alert.id,
        "login_event_id": alert.login_event_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "details": _loads(alert.details, {}),
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat(),
    }


def _detect_reasons(
    user_id: int,
    current_event_id: int,
    ip_address: str,
    user_agent: str,
    now: datetime,
) -> list[str]:
    reasons: list[str] = []
    prior_successes = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(True),
            LoginEvent.id != current_event_id,
        )
        .all()
    )

    if prior_successes:
        known_ips = {event.ip_address for event in prior_successes}
        known_agents = {event.user_agent for event in prior_successes}
        if ip_address not in known_ips:
            reasons.append("new_ip")
        if user_agent not in known_agents:
            reasons.append("new_device")
        if now.hour < 5 or now.hour >= 23:
            reasons.append("unusual_hour")

    failed_count = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(False),
            LoginEvent.occurred_at >= now - FAILED_LOGIN_WINDOW,
        )
        .count()
    )
    if failed_count >= FAILED_LOGIN_THRESHOLD:
        reasons.append("failed_login_burst")

    return reasons


def _make_alert(
    user_id: int,
    login_event_id: int,
    alert_type: str,
    ip_address: str,
    user_agent: str,
) -> SecurityAlert:
    severity = "high" if alert_type == "failed_login_burst" else "medium"
    details = {"ip_address": ip_address, "user_agent": user_agent}
    return SecurityAlert(
        user_id=user_id,
        login_event_id=login_event_id,
        alert_type=alert_type,
        severity=severity,
        message=ALERT_MESSAGES[alert_type],
        details=json.dumps(details),
    )


def _loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback
