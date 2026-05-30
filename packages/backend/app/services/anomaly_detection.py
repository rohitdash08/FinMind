import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import LoginAttempt, LoginAttemptLevel, SuspiciousActivity, User

logger = logging.getLogger("finmind.anomaly_detection")

RAPID_ATTEMPT_WINDOW_MINUTES = 5
RAPID_ATTEMPT_THRESHOLD = 5
NEW_LOCATION_THRESHOLD_HOURS = 24


def record_login_attempt(
    email: str,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    user_id: int | None = None,
    location: str | None = None,
) -> LoginAttempt:
    attempt = LoginAttempt(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        location=location,
        success=success,
        level=LoginAttemptLevel.INFO,
    )
    db.session.add(attempt)
    db.session.commit()

    if success and user_id:
        _detect_anomalies(user_id, attempt)

    return attempt


def _detect_anomalies(user_id: int, attempt: LoginAttempt) -> None:
    anomalies = []

    new_location = _detect_new_location(user_id, attempt)
    if new_location:
        anomalies.append(new_location)

    unusual_time = _detect_unusual_time(user_id, attempt)
    if unusual_time:
        anomalies.append(unusual_time)

    rapid_attempts = _detect_rapid_attempts(user_id, attempt)
    if rapid_attempts:
        anomalies.append(rapid_attempts)

    if anomalies:
        attempt.level = LoginAttemptLevel.SUSPICIOUS
        attempt.reason = "; ".join(a["description"] for a in anomalies)
        db.session.commit()

    for anomaly in anomalies:
        activity = SuspiciousActivity(
            user_id=user_id,
            activity_type=anomaly["type"],
            description=anomaly["description"],
            severity=anomaly["severity"],
            metadata_json=json.dumps(anomaly.get("metadata", {})),
        )
        db.session.add(activity)
        logger.warning(
            "Anomaly user=%s type=%s severity=%s",
            user_id, anomaly["type"], anomaly["severity"],
        )

    db.session.commit()


def _detect_new_location(user_id: int, attempt: LoginAttempt) -> dict | None:
    if not attempt.ip_address:
        return None
    window = datetime.utcnow() - timedelta(hours=NEW_LOCATION_THRESHOLD_HOURS)
    recent = (
        db.session.query(LoginAttempt.id)
        .filter(
            LoginAttempt.user_id == user_id,
            LoginAttempt.ip_address == attempt.ip_address,
            LoginAttempt.created_at >= window,
            LoginAttempt.success.is_(True),
        )
        .count()
    )
    if recent > 1:
        return None
    previous = (
        db.session.query(LoginAttempt.ip_address)
        .filter(
            LoginAttempt.user_id == user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.id != attempt.id,
        )
        .order_by(LoginAttempt.created_at.desc())
        .first()
    )
    if previous and previous[0] != attempt.ip_address:
        return {
            "type": "new_location",
            "description": f"Login from new IP {attempt.ip_address} (previous: {previous[0]})",
            "severity": "medium",
            "metadata": {"new_ip": attempt.ip_address, "previous_ip": previous[0]},
        }
    return None


def _detect_unusual_time(user_id: int, attempt: LoginAttempt) -> dict | None:
    hour = attempt.created_at.hour
    if 6 <= hour < 23:
        return None
    count = (
        db.session.query(LoginAttempt.id)
        .filter(
            LoginAttempt.user_id == user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.id != attempt.id,
        )
        .count()
    )
    if count == 0:
        return None
    late_count = (
        db.session.query(LoginAttempt.id)
        .filter(
            LoginAttempt.user_id == user_id,
            LoginAttempt.success.is_(True),
            func.extract("hour", LoginAttempt.created_at).between(0, 5),
        )
        .count()
    )
    if late_count == 0:
        return {
            "type": "unusual_time",
            "description": f"Login at unusual hour: {hour}:00",
            "severity": "low",
            "metadata": {"hour": hour},
        }
    return None


def _detect_rapid_attempts(user_id: int, attempt: LoginAttempt) -> dict | None:
    window = attempt.created_at - timedelta(minutes=RAPID_ATTEMPT_WINDOW_MINUTES)
    recent = (
        db.session.query(LoginAttempt.id)
        .filter(
            LoginAttempt.user_id == user_id,
            LoginAttempt.created_at >= window,
            LoginAttempt.id != attempt.id,
        )
        .count()
    )
    if recent >= RAPID_ATTEMPT_THRESHOLD:
        return {
            "type": "rapid_attempts",
            "description": f"{recent + 1} login attempts in {RAPID_ATTEMPT_WINDOW_MINUTES} minutes",
            "severity": "high",
            "metadata": {"attempt_count": recent + 1, "window_minutes": RAPID_ATTEMPT_WINDOW_MINUTES},
        }
    return None


def list_alerts(user_id: int, limit: int = 50) -> list[dict]:
    items = (
        db.session.query(SuspiciousActivity)
        .filter(SuspiciousActivity.user_id == user_id)
        .order_by(SuspiciousActivity.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "activity_type": a.activity_type,
            "description": a.description,
            "severity": a.severity,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]


def acknowledge_alert(alert_id: int, user_id: int) -> bool:
    alert = db.session.get(SuspiciousActivity, alert_id)
    if not alert or alert.user_id != user_id:
        return False
    alert.acknowledged = True
    db.session.commit()
    return True


def get_login_history(user_id: int, limit: int = 20) -> list[dict]:
    items = (
        db.session.query(LoginAttempt)
        .filter(LoginAttempt.user_id == user_id)
        .order_by(LoginAttempt.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "email": a.email,
            "ip_address": a.ip_address,
            "location": a.location,
            "success": a.success,
            "level": a.level.value if a.level else "INFO",
            "reason": a.reason,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]
