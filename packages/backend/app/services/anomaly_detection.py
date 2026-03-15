from datetime import datetime, timedelta
from ..extensions import db, redis_client
from ..models import LoginAttempt
import logging

logger = logging.getLogger("finmind.anomaly")

# Thresholds
RAPID_ATTEMPT_LIMIT = 5  # max attempts per minute
RAPID_ATTEMPT_WINDOW = 60  # seconds
UNUSUAL_HOUR_START = 2  # 2 AM
UNUSUAL_HOUR_END = 5  # 5 AM


def _rapid_key(user_id: int) -> str:
    return f"login:rapid:{user_id}"


def check_new_ip(user_id: int, ip: str) -> bool:
    """Return True if this IP has never been used by this user."""
    existing = (
        db.session.query(LoginAttempt)
        .filter_by(user_id=user_id, ip_address=ip, success=True)
        .first()
    )
    return existing is None


def check_new_device(user_id: int, user_agent: str) -> bool:
    """Return True if this user agent has never been seen for this user."""
    if not user_agent:
        return False
    existing = (
        db.session.query(LoginAttempt)
        .filter_by(user_id=user_id, user_agent=user_agent, success=True)
        .first()
    )
    return existing is None


def check_rapid_attempts(user_id: int) -> bool:
    """Return True if user has exceeded rapid login attempt threshold."""
    key = _rapid_key(user_id)
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, RAPID_ATTEMPT_WINDOW)
        return count > RAPID_ATTEMPT_LIMIT
    except Exception:
        logger.warning("Redis unavailable for rapid attempt check user_id=%s", user_id)
        return False


def check_unusual_time(user_id: int) -> bool:
    """Return True if current hour falls in unusual login window."""
    current_hour = datetime.utcnow().hour
    return UNUSUAL_HOUR_START <= current_hour < UNUSUAL_HOUR_END


def analyze_login(user_id: int, ip: str, user_agent: str) -> list[str]:
    """Run all anomaly checks and return list of detected anomaly types."""
    anomalies = []

    if check_rapid_attempts(user_id):
        anomalies.append("rapid_attempts")

    if check_new_ip(user_id, ip):
        anomalies.append("new_ip")

    if check_new_device(user_id, user_agent):
        anomalies.append("new_device")

    if check_unusual_time(user_id):
        anomalies.append("unusual_time")

    return anomalies
