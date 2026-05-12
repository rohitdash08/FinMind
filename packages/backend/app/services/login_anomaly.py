"""Login anomaly detection service."""

from datetime import datetime, timedelta
from typing import List

from ..extensions import db, redis_client
from ..models import LoginAttempt
import logging

logger = logging.getLogger("finmind.login_anomaly")

# Thresholds
MAX_FAILED_ATTEMPTS_WINDOW = 5  # max failures in window
FAILED_ATTEMPTS_WINDOW_MINUTES = 15
NEW_IP_LOOKBACK_DAYS = 30


def record_login_attempt(
    email: str,
    ip_address: str,
    user_agent: str | None,
    success: bool,
    user_id: int | None = None,
) -> List[str]:
    """Record a login attempt and return list of anomaly flags (empty if normal)."""
    anomaly_flags = []

    if success and user_id:
        anomaly_flags = _detect_anomalies(user_id, email, ip_address)

    if not success:
        anomaly_flags = _detect_brute_force(email, ip_address)

    attempt = LoginAttempt(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        anomaly_flags=",".join(anomaly_flags) if anomaly_flags else None,
    )
    db.session.add(attempt)
    db.session.commit()

    if anomaly_flags:
        logger.warning(
            "Login anomaly detected: email=%s ip=%s flags=%s",
            email,
            ip_address,
            anomaly_flags,
        )
        _store_alert(user_id or 0, email, anomaly_flags)

    return anomaly_flags


def _detect_anomalies(user_id: int, email: str, ip_address: str) -> List[str]:
    """Detect anomalies for a successful login."""
    flags = []

    # Check if IP is new for this user
    cutoff = datetime.utcnow() - timedelta(days=NEW_IP_LOOKBACK_DAYS)
    known_ips = (
        db.session.query(LoginAttempt.ip_address)
        .filter(
            LoginAttempt.user_id == user_id,
            LoginAttempt.success == True,
            LoginAttempt.created_at >= cutoff,
        )
        .distinct()
        .all()
    )
    known_ip_set = {row[0] for row in known_ips}
    if ip_address not in known_ip_set and len(known_ip_set) > 0:
        flags.append("new_ip")

    return flags


def _detect_brute_force(email: str, ip_address: str) -> List[str]:
    """Detect brute force attempts."""
    flags = []
    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_ATTEMPTS_WINDOW_MINUTES)

    recent_failures = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.email == email,
            LoginAttempt.success == False,
            LoginAttempt.created_at >= cutoff,
        )
        .count()
    )

    if recent_failures >= MAX_FAILED_ATTEMPTS_WINDOW:
        flags.append("brute_force")

    # Check rapid failures from same IP
    ip_failures = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.ip_address == ip_address,
            LoginAttempt.success == False,
            LoginAttempt.created_at >= cutoff,
        )
        .count()
    )
    if ip_failures >= MAX_FAILED_ATTEMPTS_WINDOW:
        flags.append("ip_brute_force")

    return flags


def _store_alert(user_id: int, email: str, flags: List[str]):
    """Store alert in Redis for the user to see on next login."""
    key = f"login_alert:{user_id or email}"
    alert = f"{datetime.utcnow().isoformat()}|{','.join(flags)}"
    redis_client.lpush(key, alert)
    redis_client.ltrim(key, 0, 9)  # keep last 10 alerts
    redis_client.expire(key, 86400 * 7)  # expire after 7 days


def get_user_alerts(user_id: int) -> List[dict]:
    """Get pending login alerts for a user."""
    key = f"login_alert:{user_id}"
    raw = redis_client.lrange(key, 0, -1)
    alerts = []
    for item in raw:
        parts = item.split("|", 1)
        if len(parts) == 2:
            alerts.append({"timestamp": parts[0], "flags": parts[1].split(",")})
    return alerts


def clear_user_alerts(user_id: int):
    """Clear alerts after user acknowledges them."""
    redis_client.delete(f"login_alert:{user_id}")
