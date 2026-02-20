"""Security service: login anomaly detection and brute-force protection."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from flask import request
from ..extensions import db, redis_client
from ..models import AuditLog

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FAIL_WINDOW_SECONDS: int = 600           # 10-minute rolling window
MAX_FAILURES: int = 5                     # brute-force threshold
LOGIN_EVENT_TTL: int = 60 * 60 * 24 * 30  # 30-day retention
SUSPICIOUS_HOUR_START: int = 1            # 01:00 UTC inclusive
SUSPICIOUS_HOUR_END: int = 5              # 05:00 UTC exclusive


# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------
def get_client_ip() -> str:
    """Return the originating client IP, honouring X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


# ---------------------------------------------------------------------------
# Brute-force / failure tracking
# ---------------------------------------------------------------------------
def record_failed_login(ip: str, email: str) -> int:
    """Increment failure counter for (ip, email); return new count.

    Key: ``auth:fails:{ip}:{email}`` with TTL = FAIL_WINDOW_SECONDS.
    """
    key = f"auth:fails:{ip}:{email}"
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, FAIL_WINDOW_SECONDS)
    count, _ = pipe.execute()
    return int(count)


def get_failure_count(ip: str, email: str) -> int:
    """Return current failure count; 0 if absent."""
    val = redis_client.get(f"auth:fails:{ip}:{email}")
    return int(val) if val else 0


def reset_failure_count(ip: str, email: str) -> None:
    """Delete failure counter after a successful login."""
    redis_client.delete(f"auth:fails:{ip}:{email}")


def is_brute_force(ip: str, email: str) -> bool:
    """Return True when the failure count has reached MAX_FAILURES."""
    return get_failure_count(ip, email) >= MAX_FAILURES


# ---------------------------------------------------------------------------
# Login event storage
# ---------------------------------------------------------------------------
def store_login_event(user_id: int, ip: str) -> None:
    """Persist a login event in Redis with a 30-day TTL.

    Key:   ``auth:login_event:{user_id}:{YYYYMMDDTHHMMSSz}``
    Value: JSON ``{ip, hour, timestamp}``
    """
    now = datetime.now(timezone.utc)
    ts_key = now.strftime("%Y%m%dT%H%M%SZ")
    key = f"auth:login_event:{user_id}:{ts_key}"
    payload = json.dumps(
        {
            "ip": ip,
            "hour": now.hour,
            "timestamp": now.isoformat(),
        }
    )
    redis_client.setex(key, LOGIN_EVENT_TTL, payload)


def get_login_events(user_id: int, limit: int = 10) -> list:
    """Return the *limit* most-recent login events for *user_id*.

    Scans ``auth:login_event:{user_id}:*``, parses JSON, sorts newest-first.
    """
    pattern = f"auth:login_event:{user_id}:*"
    keys = redis_client.keys(pattern)
    events: list = []
    for key in keys:
        raw = redis_client.get(key)
        if raw:
            try:
                events.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return events[:limit]


# ---------------------------------------------------------------------------
# Unusual-hour detection
# ---------------------------------------------------------------------------
def detect_unusual_hour() -> Optional[str]:
    """Return alert string if UTC hour is in the suspicious window, else None.

    Suspicious window: 01:00–04:59 UTC.
    """
    now = datetime.now(timezone.utc)
    if SUSPICIOUS_HOUR_START <= now.hour < SUSPICIOUS_HOUR_END:
        return f"Login detected at unusual hour ({now.strftime('%H:%M')} UTC)"
    return None


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def log_audit_event(
    action: str,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Insert an AuditLog row; silently swallows DB errors.

    Expected action values: ``login_success``, ``login_failed``,
    ``brute_force_blocked``.
    """
    try:
        kwargs = dict(action=action, user_id=user_id)
        # Only set optional columns if model supports them
        al = AuditLog(**{k: v for k, v in dict(
            action=action,
            user_id=user_id,
            ip_address=ip,
            details=details,
        ).items() if hasattr(AuditLog, k)})
        db.session.add(al)
        db.session.commit()
    except Exception:
        db.session.rollback()
