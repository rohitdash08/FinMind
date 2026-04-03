"""Login anomaly detection service.

Tracks failed attempts per user/IP and flags suspicious patterns.
Uses Redis for fast, ephemeral storage.
"""

import time
import logging
from datetime import datetime, timezone

from ..extensions import redis_client

logger = logging.getLogger("finmind.auth.anomaly")

# Configuration
MAX_FAILED_PER_HOUR = 10
MAX_FAILED_PER_IP_HOUR = 20
MAX_FAILED_PER_DAY = 30
SUSPICIOUS_IP_THRESHOLD = 5
ANOMALY_TTL = 86400  # 24 hours

PREFIX_ATTEMPTS = "auth:attempts:user:{uid}"
PREFIX_IP_ATTEMPTS = "auth:attempts:ip:{ip}"
PREFIX_ANOMALY = "auth:anomaly:{uid}"
PREFIX_IP_HISTORY = "auth:ip_history:{uid}"


def record_failed_login(user_id: int, ip: str) -> dict:
    """Record a failed login attempt and check for anomalies."""
    now = time.time()
    alerts = []

    # Track per-user failures
    user_key = PREFIX_ATTEMPTS.format(uid=user_id)
    redis_client.incr(user_key)
    redis_client.expire(user_key, 3600)
    user_failures = int(redis_client.get(user_key) or 0)

    # Track per-IP failures
    ip_key = PREFIX_IP_ATTEMPTS.format(ip=_sanitize_ip(ip))
    redis_client.incr(ip_key)
    redis_client.expire(ip_key, 3600)
    ip_failures = int(redis_client.get(ip_key) or 0)

    # Track IP history per user
    ip_history_key = PREFIX_IP_HISTORY.format(uid=user_id)
    redis_client.sadd(ip_history_key, _sanitize_ip(ip))
    redis_client.expire(ip_history_key, 86400 * 7)
    known_ips = redis_client.scard(ip_history_key)

    # Check thresholds
    if user_failures >= MAX_FAILED_PER_HOUR:
        alerts.append({
            "type": "excessive_user_failures",
            "severity": "HIGH",
            "message": f"{user_failures} failed attempts in last hour for user {user_id}",
        })

    if ip_failures >= MAX_FAILED_PER_IP_HOUR:
        alerts.append({
            "type": "excessive_ip_failures",
            "severity": "CRITICAL",
            "message": f"{ip_failures} failed attempts from IP {_sanitize_ip(ip)} in last hour",
        })

    # Check for new suspicious IP (user usually logs in from few IPs)
    if known_ips > SUSPICIOUS_IP_THRESHOLD:
        alerts.append({
            "type": "multiple_ip_usage",
            "severity": "MEDIUM",
            "message": f"User {user_id} has logged in from {known_ips} different IPs",
        })

    # Store anomaly if detected
    if alerts:
        anomaly_key = PREFIX_ANOMALY.format(uid=user_id)
        ts = datetime.now(timezone.utc).isoformat()
        for alert in alerts:
            alert["timestamp"] = ts
            alert["ip"] = _sanitize_ip(ip)
            alert["user_id"] = user_id
            redis_client.lpush(anomaly_key, str(alert))
            redis_client.expire(anomaly_key, ANOMALY_TTL)
        logger.warning("Anomaly detected for user %s from IP %s: %s alerts",
                       user_id, _sanitize_ip(ip), len(alerts))

    return {"user_failures_hour": user_failures, "ip_failures_hour": ip_failures, "alerts": alerts}


def record_successful_login(user_id: int, ip: str) -> None:
    """Record a successful login — add IP to known list, reset failure counter."""
    ip_history_key = PREFIX_IP_HISTORY.format(uid=user_id)
    redis_client.sadd(ip_history_key, _sanitize_ip(ip))
    redis_client.expire(ip_history_key, 86400 * 30)

    # Reset hourly failure counter on success
    user_key = PREFIX_ATTEMPTS.format(uid=user_id)
    redis_client.delete(user_key)


def get_anomalies(user_id: int, limit: int = 50) -> list:
    """Get recent anomalies for a user."""
    anomaly_key = PREFIX_ANOMALY.format(uid=user_id)
    try:
        raw = redis_client.lrange(anomaly_key, 0, limit - 1)
        import json
        return [json.loads(item) for item in raw]
    except Exception:
        return []


def get_all_anomalies(limit: int = 100) -> list:
    """Get all recent anomalies (admin view)."""
    all_anomalies = []
    try:
        for key in redis_client.scan_iter(match="auth:anomaly:*"):
            raw = redis_client.lrange(key, 0, limit - 1)
            import json
            for item in raw:
                all_anomalies.append(json.loads(item))
    except Exception:
        pass
    # Sort by timestamp descending
    all_anomalies.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return all_anomalies[:limit]


def _sanitize_ip(ip: str) -> str:
    """Sanitize IP to prevent injection."""
    import re
    return re.sub(r"[^0-9a-fA-F.:]", "", ip)[:45]
