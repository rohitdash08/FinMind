"""Login anomaly detection service.

Detects suspicious login patterns including:
- Brute-force attempts (repeated failures from same IP)
- New device / IP detection
- Unusual login hours (outside user's normal pattern)
- Rapid successive logins from different IPs
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from ..extensions import db, redis_client
from ..models import LoginEvent, SecurityAlert

logger = logging.getLogger("finmind.login_anomaly")

# --- Thresholds ---
FAILED_STREAK_LIMIT = 5  # failures before alert
RATE_LIMIT_WINDOW = 300  # seconds (5 min)
RATE_LIMIT_MAX = 10  # max attempts per window
UNUSUAL_HOUR_HISTORY = 30  # days of history to learn pattern
IP_VELOCITY_WINDOW = 3600  # 1 hour
IP_VELOCITY_LIMIT = 3  # max distinct IPs per window


def record_login(
    email: str,
    ip_address: str,
    user_agent: str | None,
    success: bool,
    user_id: int | None,
) -> list[dict]:
    """Record a login attempt and return any triggered anomalies."""
    event = LoginEvent(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
    )
    db.session.add(event)
    db.session.flush()

    anomalies = []

    # Check rate limiting (per IP) — graceful if Redis is unavailable
    try:
        rate_key = f"login_rate:{ip_address}"
        count = redis_client.incr(rate_key)
        if count == 1:
            redis_client.expire(rate_key, RATE_LIMIT_WINDOW)
        if count > RATE_LIMIT_MAX:
            anomalies.append(
                _create_alert(
                    user_id=user_id,
                    alert_type="rate_limit_exceeded",
                    severity="high",
                    message=f"Rate limit exceeded: {count} login attempts in {RATE_LIMIT_WINDOW}s from {ip_address}",
                    ip_address=ip_address,
                )
            )
    except Exception:
        logger.debug("Redis unavailable for rate limiting — skipping")

    if success and user_id:
        # Check failed streak before this success
        anomalies.extend(_check_failed_streak(user_id, ip_address))

        # Check new IP
        anomalies.extend(_check_new_ip(user_id, ip_address))

        # Check unusual hours
        anomalies.extend(_check_unusual_hours(user_id))

        # Check IP velocity
        anomalies.extend(_check_ip_velocity(user_id, ip_address))

    elif not success:
        # Track consecutive failures per IP — graceful if Redis unavailable
        try:
            fail_key = f"login_fails:{ip_address}"
            fails = redis_client.incr(fail_key)
            if fails == 1:
                redis_client.expire(fail_key, RATE_LIMIT_WINDOW)
            if fails >= FAILED_STREAK_LIMIT:
                anomalies.append(
                    _create_alert(
                        user_id=user_id,
                        alert_type="brute_force_suspected",
                        severity="high",
                        message=f"Possible brute-force: {fails} consecutive failed logins from {ip_address}",
                        ip_address=ip_address,
                    )
                )
        except Exception:
            logger.debug("Redis unavailable for failure tracking — skipping")

    db.session.commit()
    return anomalies


def _check_failed_streak(user_id: int, ip_address: str) -> list[dict]:
    """Alert if there were many failures before this successful login."""
    recent = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.created_at >= datetime.utcnow() - timedelta(hours=1),
        )
        .order_by(LoginEvent.created_at.desc())
        .limit(20)
        .all()
    )

    consecutive_fails = 0
    for evt in recent[1:]:  # skip the current success
        if not evt.success:
            consecutive_fails += 1
        else:
            break

    if consecutive_fails >= FAILED_STREAK_LIMIT:
        return [
            _create_alert(
                user_id=user_id,
                alert_type="failed_streak_before_login",
                severity="medium",
                message=f"Successful login after {consecutive_fails} failed attempts",
                ip_address=ip_address,
            )
        ]
    return []


def _check_new_ip(user_id: int, ip_address: str) -> list[dict]:
    """Alert on first-time IP for this user."""
    prior = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.ip_address == ip_address,
            LoginEvent.success.is_(True),
        )
        .count()
    )

    # prior == 1 means this is the only successful login from this IP (current one)
    if prior <= 1:
        return [
            _create_alert(
                user_id=user_id,
                alert_type="new_ip_address",
                severity="low",
                message=f"Login from new IP address: {ip_address}",
                ip_address=ip_address,
            )
        ]
    return []


def _check_unusual_hours(user_id: int) -> list[dict]:
    """Alert if login is outside the user's normal active hours."""
    now = datetime.utcnow()
    current_hour = now.hour

    history = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(True),
            LoginEvent.created_at
            >= now - timedelta(days=UNUSUAL_HOUR_HISTORY),
        )
        .all()
    )

    if len(history) < 5:
        # Not enough data to determine normal hours
        return []

    hours = [evt.created_at.hour for evt in history]
    hour_counts = {}
    for h in hours:
        hour_counts[h] = hour_counts.get(h, 0) + 1

    total = len(hours)
    current_hour_pct = hour_counts.get(current_hour, 0) / total

    if current_hour_pct < 0.02 and total >= 10:
        return [
            _create_alert(
                user_id=user_id,
                alert_type="unusual_login_time",
                severity="low",
                message=f"Login at unusual hour ({current_hour}:00 UTC) — less than 2% of historical logins",
                ip_address=None,
            )
        ]
    return []


def _check_ip_velocity(user_id: int, ip_address: str) -> list[dict]:
    """Alert if logins come from many different IPs in a short window."""
    recent = (
        db.session.query(LoginEvent.ip_address)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(True),
            LoginEvent.created_at
            >= datetime.utcnow() - timedelta(seconds=IP_VELOCITY_WINDOW),
        )
        .distinct()
        .all()
    )

    distinct_ips = {row[0] for row in recent}
    if len(distinct_ips) >= IP_VELOCITY_LIMIT:
        return [
            _create_alert(
                user_id=user_id,
                alert_type="ip_velocity_anomaly",
                severity="high",
                message=f"Logins from {len(distinct_ips)} different IPs in the last hour",
                ip_address=ip_address,
            )
        ]
    return []


def _create_alert(
    user_id: int | None,
    alert_type: str,
    severity: str,
    message: str,
    ip_address: str | None,
) -> dict:
    """Persist a SecurityAlert and return its dict representation."""
    if not user_id:
        return {"alert_type": alert_type, "severity": severity, "message": message}

    alert = SecurityAlert(
        user_id=user_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        ip_address=ip_address,
    )
    db.session.add(alert)
    db.session.flush()

    logger.warning("Security alert user_id=%s type=%s: %s", user_id, alert_type, message)

    return {
        "id": alert.id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "ip_address": ip_address,
    }


def get_login_history(user_id: int, limit: int = 50) -> list[dict]:
    """Return recent login events for a user."""
    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == user_id)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "ip_address": e.ip_address,
            "user_agent": e.user_agent,
            "success": e.success,
            "created_at": e.created_at.isoformat() + "Z",
        }
        for e in events
    ]


def get_security_alerts(user_id: int, include_dismissed: bool = False) -> list[dict]:
    """Return security alerts for a user."""
    query = db.session.query(SecurityAlert).filter(
        SecurityAlert.user_id == user_id
    )
    if not include_dismissed:
        query = query.filter(SecurityAlert.dismissed.is_(False))

    alerts = query.order_by(SecurityAlert.created_at.desc()).limit(100).all()
    return [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "ip_address": a.ip_address,
            "dismissed": a.dismissed,
            "created_at": a.created_at.isoformat() + "Z",
        }
        for a in alerts
    ]


def dismiss_alert(alert_id: int, user_id: int) -> bool:
    """Dismiss a security alert. Returns True if found and dismissed."""
    alert = db.session.query(SecurityAlert).filter(
        SecurityAlert.id == alert_id,
        SecurityAlert.user_id == user_id,
    ).first()
    if not alert:
        return False
    alert.dismissed = True
    db.session.commit()
    return True
