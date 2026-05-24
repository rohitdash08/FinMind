"""Login anomaly detection service (issue #124).

Public API
----------
record_login_event(user_id, ip, user_agent, success, reason) -> LoginEvent
check_and_create_alerts(user_id, event) -> list[SecurityAlert]
get_login_history(user_id, limit) -> list[LoginEvent]
get_alerts(user_id, unread_only) -> list[SecurityAlert]
acknowledge_alert(user_id, alert_id) -> SecurityAlert | None
event_to_dict(event) -> dict
alert_to_dict(alert) -> dict

Detection rules
---------------
- NEW_IP       — successful login from an IP hash not seen in last 20 successes
- NEW_DEVICE   — successful login from a UA hash not seen in last 20 successes
- FAILED_BURST — >=5 failed attempts in the last 15 minutes for this user
- UNUSUAL_HOUR — successful login between 00:00–04:59 UTC
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from ..extensions import db
from ..models import AlertSeverity, AlertType, LoginEvent, SecurityAlert

logger = logging.getLogger("finmind.anomaly")

# Tunable constants
_HISTORY_WINDOW = 20          # recent successful logins to check against
_BURST_THRESHOLD = 5          # failed attempts that trigger burst alert
_BURST_WINDOW_MINUTES = 15    # look-back window for burst detection
_UNUSUAL_HOUR_START = 0       # 00:00 UTC
_UNUSUAL_HOUR_END = 5         # 05:00 UTC (exclusive)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _mask_ip(ip: str) -> str:
    """Return 'a.b.c.xxx' for IPv4, '[prefix:xxx]' for IPv6."""
    if not ip:
        return "unknown"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    # IPv6 — mask last segment
    if ":" in ip:
        segments = ip.rsplit(":", 1)
        return f"{segments[0]}:xxx"
    return ip[:len(ip) // 2] + "***"


# ---------------------------------------------------------------------------
# Core recording
# ---------------------------------------------------------------------------

def record_login_event(
    user_id: int,
    ip: str,
    user_agent: str,
    success: bool,
    reason: str | None = None,
) -> LoginEvent:
    event = LoginEvent(
        user_id=user_id,
        ip_hash=_sha256(ip or ""),
        ua_hash=_sha256(user_agent or ""),
        ip_masked=_mask_ip(ip or ""),
        success=success,
        reason=reason,
    )
    db.session.add(event)
    db.session.flush()  # get event.id without committing yet
    return event


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def check_and_create_alerts(user_id: int, event: LoginEvent) -> list[SecurityAlert]:
    """Run all anomaly checks and persist any new SecurityAlerts.

    Should be called *before* db.session.commit() so everything is atomic.
    Only runs on successful logins except for FAILED_BURST.
    """
    alerts: list[SecurityAlert] = []

    # FAILED_BURST — check on every attempt (success or failure)
    burst_alert = _check_failed_burst(user_id, event)
    if burst_alert:
        alerts.append(burst_alert)

    if event.success:
        # Only meaningful to alert for new IP/device on successful logins
        new_ip_alert = _check_new_ip(user_id, event)
        if new_ip_alert:
            alerts.append(new_ip_alert)

        new_dev_alert = _check_new_device(user_id, event)
        if new_dev_alert:
            alerts.append(new_dev_alert)

        unusual_alert = _check_unusual_hour(user_id, event)
        if unusual_alert:
            alerts.append(unusual_alert)

    for alert in alerts:
        db.session.add(alert)

    return alerts


def _check_new_ip(user_id: int, event: LoginEvent) -> SecurityAlert | None:
    """Alert if this IP hash hasn't been seen in the last N successful logins."""
    recent_hashes = (
        db.session.query(LoginEvent.ip_hash)
        .filter_by(user_id=user_id, success=True)
        .filter(LoginEvent.id != event.id)
        .order_by(LoginEvent.created_at.desc())
        .limit(_HISTORY_WINDOW)
        .all()
    )
    seen = {row[0] for row in recent_hashes}

    # Brand-new user with no history — don't alert on first login
    if not seen:
        return None

    if event.ip_hash not in seen:
        return SecurityAlert(
            user_id=user_id,
            alert_type=AlertType.NEW_IP.value,
            severity=AlertSeverity.MEDIUM.value,
            message=(
                f"Login from a new IP address ({event.ip_masked}). "
                "If this wasn't you, please change your password immediately."
            ),
            event_id=event.id,
        )
    return None


def _check_new_device(user_id: int, event: LoginEvent) -> SecurityAlert | None:
    """Alert if this user-agent hash hasn't been seen in the last N successful logins."""
    recent_hashes = (
        db.session.query(LoginEvent.ua_hash)
        .filter_by(user_id=user_id, success=True)
        .filter(LoginEvent.id != event.id)
        .order_by(LoginEvent.created_at.desc())
        .limit(_HISTORY_WINDOW)
        .all()
    )
    seen = {row[0] for row in recent_hashes}

    if not seen:
        return None

    if event.ua_hash not in seen:
        return SecurityAlert(
            user_id=user_id,
            alert_type=AlertType.NEW_DEVICE.value,
            severity=AlertSeverity.MEDIUM.value,
            message=(
                "Login from a new device or browser detected. "
                "If this wasn't you, please change your password immediately."
            ),
            event_id=event.id,
        )
    return None


def _check_failed_burst(user_id: int, event: LoginEvent) -> SecurityAlert | None:
    """Alert if there are >=BURST_THRESHOLD failed attempts in the last window."""
    cutoff = datetime.utcnow() - timedelta(minutes=_BURST_WINDOW_MINUTES)
    # Don't count the current event since it's not committed yet
    failed_count = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(False),
            LoginEvent.created_at >= cutoff,
            LoginEvent.id != event.id,
        )
        .count()
    )

    # Add current event if it's also a failure
    if not event.success:
        failed_count += 1

    if failed_count >= _BURST_THRESHOLD:
        # Avoid duplicate burst alerts — check if one was created recently
        existing = (
            db.session.query(SecurityAlert)
            .filter(
                SecurityAlert.user_id == user_id,
                SecurityAlert.alert_type == AlertType.FAILED_BURST.value,
                SecurityAlert.created_at >= cutoff,
            )
            .first()
        )
        if existing:
            return None  # already alerted for this burst window

        return SecurityAlert(
            user_id=user_id,
            alert_type=AlertType.FAILED_BURST.value,
            severity=AlertSeverity.HIGH.value,
            message=(
                f"{failed_count} failed login attempts in the last "
                f"{_BURST_WINDOW_MINUTES} minutes. "
                "Your account may be under a brute-force attack."
            ),
            event_id=event.id,
        )
    return None


def _check_unusual_hour(user_id: int, event: LoginEvent) -> SecurityAlert | None:
    """Alert on login between 00:00 and 04:59 UTC."""
    hour = event.created_at.hour
    if _UNUSUAL_HOUR_START <= hour < _UNUSUAL_HOUR_END:
        return SecurityAlert(
            user_id=user_id,
            alert_type=AlertType.UNUSUAL_HOUR.value,
            severity=AlertSeverity.LOW.value,
            message=(
                f"Login at {event.created_at.strftime('%H:%M')} UTC — "
                "outside your usual activity window."
            ),
            event_id=event.id,
        )
    return None


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_login_history(user_id: int, limit: int = 50) -> list[LoginEvent]:
    return (
        db.session.query(LoginEvent)
        .filter_by(user_id=user_id)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )


def get_alerts(user_id: int, unread_only: bool = False) -> list[SecurityAlert]:
    q = db.session.query(SecurityAlert).filter_by(user_id=user_id)
    if unread_only:
        q = q.filter_by(acknowledged=False)
    return q.order_by(SecurityAlert.created_at.desc()).all()


def acknowledge_alert(user_id: int, alert_id: int) -> SecurityAlert | None:
    alert = (
        db.session.query(SecurityAlert)
        .filter_by(id=alert_id, user_id=user_id)
        .first()
    )
    if not alert:
        return None
    alert.acknowledged = True
    db.session.commit()
    logger.info("Alert id=%s acknowledged by user=%s", alert_id, user_id)
    return alert


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def event_to_dict(event: LoginEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "ip_masked": event.ip_masked,
        "success": event.success,
        "reason": event.reason,
        "created_at": event.created_at.isoformat(),
    }


def alert_to_dict(alert: SecurityAlert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "acknowledged": alert.acknowledged,
        "event_id": alert.event_id,
        "created_at": alert.created_at.isoformat(),
    }
