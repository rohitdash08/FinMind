"""
Login anomaly detection service.

Tracks login attempts per IP/email in Redis and flags suspicious patterns:
- More than 3 failed attempts from the same IP within 15 minutes
- More than 5 failed attempts for the same email within 1 hour
- Stores the 20 most recent login events per user for the security-alerts endpoint
"""

import json
import logging
import time

from ..extensions import redis_client

logger = logging.getLogger("finmind.security")

_FAIL_IP_KEY = "security:fails:ip:{ip}"
_FAIL_EMAIL_KEY = "security:fails:email:{email}"
_EVENTS_KEY = "security:events:{user_id}"

_IP_FAIL_LIMIT = 3
_IP_FAIL_WINDOW = 900  # 15 minutes
_EMAIL_FAIL_LIMIT = 5
_EMAIL_FAIL_WINDOW = 3600  # 1 hour
_MAX_EVENTS = 20
_EVENTS_TTL = 30 * 24 * 3600  # 30 days


def record_login_attempt(
    email: str,
    ip: str,
    success: bool,
    user_id: int | None = None,
) -> None:
    """
    Record a login attempt and log suspicious patterns.

    On success: clears failure counters and appends a login_success event.
    On failure: increments per-IP and per-email counters, appends a
    login_failed or suspicious_login event when thresholds are exceeded.
    All Redis errors are caught so the login flow is never disrupted.
    """
    try:
        ip_key = _FAIL_IP_KEY.format(ip=ip)
        email_key = _FAIL_EMAIL_KEY.format(email=email)

        if success:
            redis_client.delete(ip_key, email_key)
            if user_id is not None:
                _append_event(user_id, ip, email, "login_success", "Login successful")
        else:
            pipe = redis_client.pipeline()
            pipe.incr(ip_key)
            pipe.expire(ip_key, _IP_FAIL_WINDOW)
            pipe.incr(email_key)
            pipe.expire(email_key, _EMAIL_FAIL_WINDOW)
            ip_count, _, email_count, _ = pipe.execute()

            suspicious = ip_count > _IP_FAIL_LIMIT or email_count > _EMAIL_FAIL_LIMIT
            if suspicious:
                logger.warning(
                    "Suspicious login activity — ip=%s ip_fails=%d email_fails=%d",
                    ip,
                    ip_count,
                    email_count,
                )

            if user_id is not None:
                event_type = "suspicious_login" if suspicious else "login_failed"
                _append_event(
                    user_id,
                    ip,
                    email,
                    event_type,
                    _build_alert_msg(ip_count, email_count),
                )

    except Exception:
        logger.exception("Error recording login attempt — anomaly detection skipped")


def get_security_alerts(user_id: int, limit: int = 20) -> list[dict]:
    """
    Return the most recent security events for a user (newest first).
    Each event has: type, ip, email, ts (Unix timestamp), msg
    """
    try:
        raw = redis_client.lrange(_EVENTS_KEY.format(user_id=user_id), 0, limit - 1)
        events = []
        for item in raw:
            try:
                events.append(json.loads(item))
            except (ValueError, TypeError):
                continue
        return events
    except Exception:
        logger.exception("Error fetching security alerts for user_id=%s", user_id)
        return []


# ── private helpers ──────────────────────────────────────────────────────────


def _append_event(user_id: int, ip: str, email: str, event_type: str, msg: str) -> None:
    key = _EVENTS_KEY.format(user_id=user_id)
    event = json.dumps(
        {
            "type": event_type,
            "ip": ip,
            "email": email,
            "ts": int(time.time()),
            "msg": msg,
        }
    )
    pipe = redis_client.pipeline()
    pipe.lpush(key, event)
    pipe.ltrim(key, 0, _MAX_EVENTS - 1)
    pipe.expire(key, _EVENTS_TTL)
    pipe.execute()


def _build_alert_msg(ip_count: int, email_count: int) -> str:
    parts = []
    if ip_count > _IP_FAIL_LIMIT:
        parts.append(f"IP exceeded failed-login limit ({ip_count} attempts in 15 min)")
    if email_count > _EMAIL_FAIL_LIMIT:
        parts.append(
            f"account exceeded failed-login limit ({email_count} attempts in 1 hr)"
        )
    return "; ".join(parts) if parts else "Failed login attempt"
