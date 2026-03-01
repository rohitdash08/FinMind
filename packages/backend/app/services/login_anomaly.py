"""Login anomaly detection service.

Detects suspicious login activity by analysing login history for:
- New / previously-unseen IP addresses
- New / previously-unseen user agents (device fingerprint proxy)
- Unusual login hour (outside user's typical window)
- Multiple consecutive failed login attempts (brute-force signal)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from ..extensions import db
from ..models import LoginHistory, SecurityAlert, User
from .reminders import send_email

logger = logging.getLogger("finmind.login_anomaly")

# Thresholds
FAILED_ATTEMPT_THRESHOLD = 5  # in a rolling window
FAILED_ATTEMPT_WINDOW_MINUTES = 30
UNUSUAL_HOUR_START = 1  # 01:00 UTC
UNUSUAL_HOUR_END = 5  # 05:00 UTC


def record_login(
    user_id: int,
    ip_address: str | None,
    user_agent: str | None,
    success: bool,
) -> LoginHistory:
    """Record a login attempt and run anomaly checks on success."""
    anomaly_flags: List[str] = []

    if success:
        anomaly_flags = _detect_anomalies(user_id, ip_address, user_agent)

    entry = LoginHistory(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        anomaly_flags=json.dumps(anomaly_flags) if anomaly_flags else None,
    )
    db.session.add(entry)

    # Also check brute-force even on success (alert that there *were* many failures)
    if success:
        recent_failures = _count_recent_failures(user_id)
        if recent_failures >= FAILED_ATTEMPT_THRESHOLD:
            anomaly_flags.append("multiple_failed_attempts")
            entry.anomaly_flags = json.dumps(anomaly_flags)

    if anomaly_flags:
        _create_alerts(user_id, anomaly_flags, ip_address, user_agent)

    db.session.commit()
    return entry


def record_failed_login(
    email: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Record a failed login. We need the user to exist to track."""
    user = db.session.query(User).filter_by(email=email).first()
    if not user:
        return  # no user to track against

    entry = LoginHistory(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False,
    )
    db.session.add(entry)

    recent_failures = _count_recent_failures(user.id)
    if recent_failures >= FAILED_ATTEMPT_THRESHOLD:
        _create_alerts(
            user.id, ["multiple_failed_attempts"], ip_address, user_agent
        )

    db.session.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_anomalies(
    user_id: int,
    ip_address: str | None,
    user_agent: str | None,
) -> List[str]:
    flags: List[str] = []

    # New IP?
    if ip_address:
        known_ip = (
            db.session.query(LoginHistory)
            .filter_by(user_id=user_id, ip_address=ip_address, success=True)
            .first()
        )
        if not known_ip:
            flags.append("new_ip")

    # New user-agent / device?
    if user_agent:
        known_ua = (
            db.session.query(LoginHistory)
            .filter_by(user_id=user_id, user_agent=user_agent, success=True)
            .first()
        )
        if not known_ua:
            flags.append("new_device")

    # Unusual hour?
    now = datetime.utcnow()
    if UNUSUAL_HOUR_START <= now.hour < UNUSUAL_HOUR_END:
        flags.append("unusual_time")

    return flags


def _count_recent_failures(user_id: int) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_ATTEMPT_WINDOW_MINUTES)
    return (
        db.session.query(LoginHistory)
        .filter(
            LoginHistory.user_id == user_id,
            LoginHistory.success == False,  # noqa: E712
            LoginHistory.created_at >= cutoff,
        )
        .count()
    )


def _create_alerts(
    user_id: int,
    flags: List[str],
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    messages = {
        "new_ip": f"Login from a new IP address: {ip_address}",
        "new_device": f"Login from a new device: {(user_agent or '')[:80]}",
        "unusual_time": "Login at an unusual hour (UTC 01:00-05:00)",
        "multiple_failed_attempts": (
            f"Multiple failed login attempts detected from IP {ip_address}"
        ),
    }

    metadata = json.dumps({"ip": ip_address, "user_agent": user_agent})

    for flag in flags:
        # Avoid duplicate unacknowledged alerts of same type within 1 hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        existing = (
            db.session.query(SecurityAlert)
            .filter(
                SecurityAlert.user_id == user_id,
                SecurityAlert.alert_type == flag,
                SecurityAlert.acknowledged == False,  # noqa: E712
                SecurityAlert.created_at >= cutoff,
            )
            .first()
        )
        if existing:
            continue

        alert = SecurityAlert(
            user_id=user_id,
            alert_type=flag,
            message=messages.get(flag, flag),
            metadata_json=metadata,
        )
        db.session.add(alert)

    # Best-effort email notification
    _notify_user(user_id, flags, messages)


def _notify_user(
    user_id: int, flags: List[str], messages: dict[str, str]
) -> None:
    user = db.session.get(User, user_id)
    if not user:
        return
    body_lines = [messages.get(f, f) for f in flags]
    body = (
        "FinMind Security Alert\n\n"
        "We detected suspicious activity on your account:\n\n"
        + "\n".join(f"• {line}" for line in body_lines)
        + "\n\nIf this was you, you can safely ignore this message. "
        "Otherwise, please change your password immediately."
    )
    try:
        send_email(user.email, "FinMind Security Alert", body)
    except Exception:
        logger.debug("Email notification failed for user %s", user_id)
