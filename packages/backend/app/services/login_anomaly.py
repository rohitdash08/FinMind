"""Login anomaly detection & suspicious activity alerts.

Tracks login attempts, detects anomalies (new device, new location,
unusual time, brute force), and alerts users.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from ..extensions import db


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(500), default="")
    country = db.Column(db.String(100), default="unknown")
    city = db.Column(db.String(100), default="unknown")
    success = db.Column(db.Boolean, default=True)
    anomaly_score = db.Column(db.Float, default=0)
    anomaly_reasons = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrustedDevice(db.Model):
    __tablename__ = "trusted_devices"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    device_fingerprint = db.Column(db.String(200), nullable=False)
    device_name = db.Column(db.String(200), default="Unknown Device")
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    trusted = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SecurityAlert(db.Model):
    __tablename__ = "security_alerts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)  # new_device, new_location, brute_force, unusual_time
    severity = db.Column(db.String(20), default="medium")  # low, medium, high, critical
    message = db.Column(db.String(500), nullable=False)
    login_attempt_id = db.Column(db.Integer, db.ForeignKey("login_attempts.id"), nullable=True)
    acknowledged = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def record_login(user_id: int, ip_address: str, user_agent: str = "",
                 country: str = "unknown", city: str = "unknown", success: bool = True) -> dict:
    """Record a login attempt and check for anomalies."""
    attempt = LoginAttempt(
        user_id=user_id, ip_address=ip_address, user_agent=user_agent,
        country=country, city=city, success=success,
    )
    db.session.add(attempt)
    db.session.flush()

    score, reasons = _analyze_anomaly(user_id, attempt)
    attempt.anomaly_score = score
    attempt.anomaly_reasons = "|".join(reasons)

    alerts = []
    if score > 0:
        for reason in reasons:
            alert = _create_alert(user_id, attempt, reason, score)
            alerts.append(alert)

    db.session.commit()

    return {
        "login_id": attempt.id,
        "anomaly_score": score,
        "anomaly_reasons": reasons,
        "alerts": [_serialize_alert(a) for a in alerts],
    }


def get_login_history(user_id: int, limit: int = 50) -> list[dict]:
    attempts = (LoginAttempt.query.filter_by(user_id=user_id)
                .order_by(LoginAttempt.created_at.desc()).limit(limit).all())
    return [_serialize_attempt(a) for a in attempts]


def get_alerts(user_id: int, unacknowledged_only: bool = False) -> list[dict]:
    q = SecurityAlert.query.filter_by(user_id=user_id)
    if unacknowledged_only:
        q = q.filter_by(acknowledged=False)
    return [_serialize_alert(a) for a in q.order_by(SecurityAlert.created_at.desc()).all()]


def acknowledge_alert(user_id: int, alert_id: int) -> bool:
    alert = SecurityAlert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return False
    alert.acknowledged = True
    db.session.commit()
    return True


def get_security_summary(user_id: int, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)

    attempts = LoginAttempt.query.filter(
        LoginAttempt.user_id == user_id, LoginAttempt.created_at >= since
    ).all()

    total = len(attempts)
    failed = sum(1 for a in attempts if not a.success)
    anomalous = sum(1 for a in attempts if a.anomaly_score > 0)
    unique_ips = len(set(a.ip_address for a in attempts))
    unique_countries = len(set(a.country for a in attempts if a.country != "unknown"))

    unack_alerts = SecurityAlert.query.filter(
        SecurityAlert.user_id == user_id, SecurityAlert.acknowledged == False,
        SecurityAlert.created_at >= since
    ).count()

    if failed > total * 0.3 or anomalous > 5:
        risk = "high"
    elif failed > total * 0.1 or anomalous > 2:
        risk = "medium"
    else:
        risk = "low"

    return {
        "period_days": days,
        "total_logins": total,
        "failed_logins": failed,
        "anomalous_logins": anomalous,
        "unique_ips": unique_ips,
        "unique_countries": unique_countries,
        "unacknowledged_alerts": unack_alerts,
        "risk_level": risk,
    }


def _analyze_anomaly(user_id: int, attempt: LoginAttempt) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    since = datetime.utcnow() - timedelta(days=30)

    history = LoginAttempt.query.filter(
        LoginAttempt.user_id == user_id, LoginAttempt.id != attempt.id,
        LoginAttempt.created_at >= since
    ).all()

    if not history:
        return 0, []

    # New IP
    known_ips = set(h.ip_address for h in history)
    if attempt.ip_address not in known_ips:
        score += 30
        reasons.append("new_ip")

    # New country
    known_countries = set(h.country for h in history if h.country != "unknown")
    if attempt.country != "unknown" and attempt.country not in known_countries and known_countries:
        score += 40
        reasons.append("new_country")

    # Brute force: >5 failed in last 15 min
    recent = datetime.utcnow() - timedelta(minutes=15)
    recent_failed = sum(1 for h in history if not h.success and h.created_at >= recent)
    if not attempt.success:
        recent_failed += 1
    if recent_failed >= 5:
        score += 50
        reasons.append("brute_force")

    # Unusual hour (user's typical login hours)
    hours = [h.created_at.hour for h in history if h.success]
    if hours:
        avg_hour = sum(hours) / len(hours)
        current_hour = attempt.created_at.hour
        diff = min(abs(current_hour - avg_hour), 24 - abs(current_hour - avg_hour))
        if diff > 8:
            score += 20
            reasons.append("unusual_time")

    return min(score, 100), reasons


def _create_alert(user_id: int, attempt: LoginAttempt, reason: str, score: float) -> SecurityAlert:
    severity_map = {
        "brute_force": "critical",
        "new_country": "high",
        "new_ip": "medium",
        "unusual_time": "low",
    }
    messages = {
        "brute_force": f"Multiple failed login attempts from {attempt.ip_address}",
        "new_country": f"Login from new country: {attempt.country} ({attempt.ip_address})",
        "new_ip": f"Login from new IP address: {attempt.ip_address}",
        "unusual_time": f"Login at unusual time from {attempt.ip_address}",
    }

    alert = SecurityAlert(
        user_id=user_id, alert_type=reason,
        severity=severity_map.get(reason, "medium"),
        message=messages.get(reason, f"Anomaly detected: {reason}"),
        login_attempt_id=attempt.id,
    )
    db.session.add(alert)
    return alert


def _serialize_attempt(a: LoginAttempt) -> dict:
    return {
        "id": a.id, "ip_address": a.ip_address, "user_agent": a.user_agent,
        "country": a.country, "city": a.city, "success": a.success,
        "anomaly_score": a.anomaly_score,
        "anomaly_reasons": a.anomaly_reasons.split("|") if a.anomaly_reasons else [],
        "created_at": a.created_at.isoformat(),
    }


def _serialize_alert(a: SecurityAlert) -> dict:
    return {
        "id": a.id, "alert_type": a.alert_type, "severity": a.severity,
        "message": a.message, "acknowledged": a.acknowledged,
        "created_at": a.created_at.isoformat(),
    }
