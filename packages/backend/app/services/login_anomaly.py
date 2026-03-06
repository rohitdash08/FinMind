import json
from datetime import datetime, timedelta
from ..extensions import db
from ..models import LoginEvent


def record_login(user_id: int, ip_address: str, user_agent: str, success: bool = True):
    """Record a login event and run anomaly detection."""
    login_time = datetime.utcnow()
    score, reasons = detect_anomalies(user_id, ip_address, user_agent, login_time, success)
    event = LoginEvent(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        login_at=login_time,
        success=success,
        anomaly_score=score,
        anomaly_reasons=json.dumps(reasons) if reasons else None,
    )
    db.session.add(event)
    db.session.commit()
    return event


def detect_anomalies(user_id: int, ip_address: str, user_agent: str,
                     login_time: datetime, success: bool = True):
    """Run all anomaly checks and return (score, reasons)."""
    reasons = []
    score = 0.0

    if success:
        if _check_new_ip(user_id, ip_address):
            reasons.append("new_ip")
            score += 0.3

        if _check_new_device(user_id, user_agent):
            reasons.append("new_device")
            score += 0.3

    if _check_brute_force(user_id):
        reasons.append("brute_force")
        score += 0.5

    if _check_odd_hours(login_time):
        reasons.append("odd_hour")
        score += 0.2

    score = min(score, 1.0)
    return score, reasons


def _check_new_ip(user_id: int, ip_address: str) -> bool:
    """Check if this IP has never been used by the user before."""
    existing = (
        db.session.query(LoginEvent)
        .filter_by(user_id=user_id, ip_address=ip_address, success=True)
        .first()
    )
    return existing is None


def _check_new_device(user_id: int, user_agent: str) -> bool:
    """Check if this user agent has never been seen for the user."""
    existing = (
        db.session.query(LoginEvent)
        .filter_by(user_id=user_id, user_agent=user_agent, success=True)
        .first()
    )
    return existing is None


def _check_brute_force(user_id: int) -> bool:
    """Check for more than 5 failed login attempts in the last 15 minutes."""
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    failed_count = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success == False,  # noqa: E712
            LoginEvent.login_at >= cutoff,
        )
        .count()
    )
    return failed_count >= 5


def _check_odd_hours(login_time: datetime) -> bool:
    """Check if login is between 2-5 AM UTC."""
    return 2 <= login_time.hour < 5


def get_login_history(user_id: int, limit: int = 20):
    """Return recent login events for a user."""
    events = (
        db.session.query(LoginEvent)
        .filter_by(user_id=user_id)
        .order_by(LoginEvent.login_at.desc())
        .limit(limit)
        .all()
    )
    return [_event_to_dict(e) for e in events]


def get_anomalies(user_id: int, limit: int = 20):
    """Return login events with anomaly_score > 0."""
    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == user_id, LoginEvent.anomaly_score > 0)
        .order_by(LoginEvent.login_at.desc())
        .limit(limit)
        .all()
    )
    return [_event_to_dict(e) for e in events]


def get_login_stats(user_id: int):
    """Return summary stats for the user."""
    unique_ips = (
        db.session.query(db.func.count(db.distinct(LoginEvent.ip_address)))
        .filter_by(user_id=user_id, success=True)
        .scalar()
    ) or 0

    unique_devices = (
        db.session.query(db.func.count(db.distinct(LoginEvent.user_agent)))
        .filter_by(user_id=user_id, success=True)
        .scalar()
    ) or 0

    total_logins = (
        db.session.query(db.func.count(LoginEvent.id))
        .filter_by(user_id=user_id)
        .scalar()
    ) or 0

    last_anomaly = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == user_id, LoginEvent.anomaly_score > 0)
        .order_by(LoginEvent.login_at.desc())
        .first()
    )

    return {
        "unique_ips": unique_ips,
        "unique_devices": unique_devices,
        "total_logins": total_logins,
        "last_anomaly": _event_to_dict(last_anomaly) if last_anomaly else None,
    }


def _event_to_dict(event: LoginEvent) -> dict:
    reasons = []
    if event.anomaly_reasons:
        try:
            reasons = json.loads(event.anomaly_reasons)
        except (json.JSONDecodeError, TypeError):
            reasons = []
    return {
        "id": event.id,
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "login_at": event.login_at.isoformat() if event.login_at else None,
        "success": event.success,
        "anomaly_score": event.anomaly_score,
        "anomaly_reasons": reasons,
    }
