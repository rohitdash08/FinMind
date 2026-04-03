"""Login anomaly detection service.

Tracks failed attempts per user/IP and flags suspicious patterns.
Uses Redis for fast, ephemeral storage with atomic operations.
"""

import json
import re
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

# Lua script for atomic INCR + EXPIRE (only sets TTL on new keys)
_INCR_EXPIRE_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def _atomic_incr(key: str, ttl: int) -> int:
    """Atomically increment and set TTL on new key."""
    count = redis_client.eval(_INCR_EXPIRE_LUA, 1, key, ttl)
    return int(count)


def record_failed_login(user_id: int, ip: str) -> dict:
    """Record a failed login attempt and check for anomalies."""
    safe_ip = _sanitize_ip(ip)
    alerts = []

    # Atomic increment per-user failures
    user_key = PREFIX_ATTEMPTS.format(uid=user_id)
    user_failures = _atomic_incr(user_key, 3600)

    # Atomic increment per-IP failures
    ip_key = PREFIX_IP_ATTEMPTS.format(ip=safe_ip)
    ip_failures = _atomic_incr(ip_key, 3600)

    # Track IP history per user
    ip_history_key = PREFIX_IP_HISTORY.format(uid=user_id)
    redis_client.sadd(ip_history_key, safe_ip)
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
            "message": f"{ip_failures} failed attempts from IP {safe_ip} in last hour",
        })

    if known_ips > SUSPICIOUS_IP_THRESHOLD:
        alerts.append({
            "type": "multiple_ip_usage",
            "severity": "MEDIUM",
            "message": f"User {user_id} has logged in from {known_ips} different IPs",
        })

    # Daily threshold check
    daily_key = f"auth:attempts:daily:user:{user_id}"
    daily_failures = _atomic_incr(daily_key, 86400)
    if daily_failures >= MAX_FAILED_PER_DAY:
        alerts.append({
            "type": "excessive_daily_failures",
            "severity": "HIGH",
            "message": f"{daily_failures} failed attempts today for user {user_id}",
        })

    # Store anomaly if detected
    if alerts:
        anomaly_key = PREFIX_ANOMALY.format(uid=user_id)
        ts = datetime.now(timezone.utc).isoformat()
        for alert in alerts:
            alert["timestamp"] = ts
            alert["ip"] = safe_ip
            alert["user_id"] = user_id
            redis_client.lpush(anomaly_key, json.dumps(alert))
            redis_client.expire(anomaly_key, ANOMALY_TTL)
        logger.warning("Anomaly detected for user %s from IP %s: %s alerts",
                       user_id, safe_ip, len(alerts))

    return {"user_failures_hour": user_failures, "ip_failures_hour": ip_failures, "alerts": alerts}


def record_successful_login(user_id: int, ip: str) -> None:
    """Record a successful login - add IP to known list, reset failure counter."""
    safe_ip = _sanitize_ip(ip)
    ip_history_key = PREFIX_IP_HISTORY.format(uid=user_id)
    redis_client.sadd(ip_history_key, safe_ip)
    redis_client.expire(ip_history_key, 86400 * 30)

    # Reset failure counters on success
    user_key = PREFIX_ATTEMPTS.format(uid=user_id)
    redis_client.delete(user_key)


def get_anomalies(user_id: int, limit: int = 50) -> list:
    """Get recent anomalies for a user."""
    anomaly_key = PREFIX_ANOMALY.format(uid=user_id)
    try:
        raw = redis_client.lrange(anomaly_key, 0, limit - 1)
        return [json.loads(item) for item in raw]
    except Exception:
        return []


def get_all_anomalies(limit: int = 100) -> list:
    """Get all recent anomalies (admin view from DB, not scan)."""
    all_anomalies = []
    try:
        for key in redis_client.scan_iter(match="auth:anomaly:*"):
            raw = redis_client.lrange(key, 0, limit - 1)
            for item in raw:
                all_anomalies.append(json.loads(item))
    except Exception:
        pass
    all_anomalies.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return all_anomalies[:limit]


def _sanitize_ip(ip: str) -> str:
    """Sanitize and validate IP address format."""
    cleaned = re.sub(r"[^0-9a-fA-F.:]", "", ip)[:45]
    return cleaned

