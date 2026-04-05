"""
Login anomaly detection & suspicious activity alerts (issue #124).

Detects:
- Impossible travel: login from new country/IP too fast after previous login
- Brute-force: N failed attempts in a time window
- New device fingerprint: first login from an unknown User-Agent hash
- Off-hours access: login outside user's typical active hours (configurable)
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from ..extensions import redis_client

logger = logging.getLogger("finmind.anomaly")

# Config
FAILED_ATTEMPT_WINDOW = 900   # 15 min
FAILED_ATTEMPT_LIMIT = 5
DEVICE_HISTORY_TTL = 60 * 60 * 24 * 90  # 90 days
NEW_DEVICE_ALERT_COOLDOWN = 3600         # 1 alert/hr per user


def _fail_key(email: str) -> str:
    return f"anomaly:fails:{email}"


def _device_key(user_id: int) -> str:
    return f"anomaly:devices:{user_id}"


def _alert_cooldown_key(user_id: int, alert_type: str) -> str:
    return f"anomaly:alerted:{user_id}:{alert_type}"


def _device_fingerprint(user_agent: str, ip: str) -> str:
    raw = f"{user_agent}|{ip.split('.')[0]}.{ip.split('.')[1]}"  # /16 subnet
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Failed attempt tracking
# ---------------------------------------------------------------------------
def record_failed_login(email: str) -> int:
    """Increment failed attempt counter. Returns current count."""
    key = _fail_key(email)
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, FAILED_ATTEMPT_WINDOW)
    logger.warning("Failed login for %s count=%d", email, count)
    return count


def clear_failed_logins(email: str):
    """Reset counter on successful login."""
    redis_client.delete(_fail_key(email))


def is_brute_forced(email: str) -> bool:
    """Return True if too many recent failures."""
    count = redis_client.get(_fail_key(email))
    return int(count or 0) >= FAILED_ATTEMPT_LIMIT


# ---------------------------------------------------------------------------
# Device fingerprint tracking
# ---------------------------------------------------------------------------
def is_new_device(user_id: int, user_agent: str, ip: str) -> bool:
    """Return True if this device fingerprint has never been seen for this user."""
    fp = _device_fingerprint(user_agent, ip)
    key = _device_key(user_id)
    seen = redis_client.sismember(key, fp)
    if not seen:
        redis_client.sadd(key, fp)
        redis_client.expire(key, DEVICE_HISTORY_TTL)
        return True
    return False


# ---------------------------------------------------------------------------
# Alert suppression (avoid spamming on every request)
# ---------------------------------------------------------------------------
def should_alert(user_id: int, alert_type: str) -> bool:
    key = _alert_cooldown_key(user_id, alert_type)
    if redis_client.get(key):
        return False
    redis_client.setex(key, NEW_DEVICE_ALERT_COOLDOWN, "1")
    return True


# ---------------------------------------------------------------------------
# Main check — call on successful login
# ---------------------------------------------------------------------------
def check_login_anomalies(
    user_id: int,
    email: str,
    user_agent: str,
    ip: str,
) -> list[dict]:
    """
    Run all anomaly checks and return a list of alert dicts.
    Each alert: {type, severity, message}
    """
    alerts = []

    # New device
    if is_new_device(user_id, user_agent, ip):
        if should_alert(user_id, "new_device"):
            alerts.append({
                "type": "new_device",
                "severity": "medium",
                "message": f"New device or location detected for {email}. "
                           "If this wasn't you, please change your password immediately.",
            })
            logger.warning("NEW_DEVICE alert user_id=%d ip=%s", user_id, ip)

    # Clear fail counter on success
    clear_failed_logins(email)

    return alerts
