"""Login anomaly detection & suspicious activity alerts.

Detects:
- New IP address (never seen before for this user)
- New user agent / device
- Rapid failed attempts (>3 failures in 10 minutes)
- Login after long inactivity (>30 days)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import LoginEvent


# Thresholds
FAILED_ATTEMPT_WINDOW_MINUTES = 10
FAILED_ATTEMPT_THRESHOLD = 3
INACTIVITY_DAYS = 30


def record_login(
    user_id: int,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Record a login event and run anomaly checks.

    Returns a dict with the event details and any flags raised.
    """
    reasons: list[str] = []

    if success:
        # Check 1: New IP
        if ip_address and _is_new_ip(user_id, ip_address):
            reasons.append("new_ip_address")

        # Check 2: New user agent
        if user_agent and _is_new_user_agent(user_id, user_agent):
            reasons.append("new_user_agent")

        # Check 3: Login after long inactivity
        if _is_inactive_user(user_id):
            reasons.append("login_after_inactivity")

    # Check 4: Rapid failed attempts (applies to both success/failure)
    if _has_rapid_failures(user_id):
        reasons.append("rapid_failed_attempts")

    flagged = len(reasons) > 0

    event = LoginEvent(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        flagged=flagged,
        flag_reasons=json.dumps(reasons) if reasons else None,
    )
    db.session.add(event)
    db.session.commit()

    return {
        "id": event.id,
        "user_id": user_id,
        "success": success,
        "ip_address": ip_address,
        "flagged": flagged,
        "flag_reasons": reasons,
        "created_at": event.created_at.isoformat(),
    }


def get_login_history(user_id: int, limit: int = 20) -> list[dict]:
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
            "success": e.success,
            "ip_address": e.ip_address,
            "user_agent": e.user_agent,
            "flagged": e.flagged,
            "flag_reasons": json.loads(e.flag_reasons) if e.flag_reasons else [],
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


def get_suspicious_activity(user_id: int) -> list[dict]:
    """Return only flagged login events."""
    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == user_id, LoginEvent.flagged.is_(True))
        .order_by(LoginEvent.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": e.id,
            "success": e.success,
            "ip_address": e.ip_address,
            "user_agent": e.user_agent,
            "flag_reasons": json.loads(e.flag_reasons) if e.flag_reasons else [],
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
# Anomaly detection helpers
# ---------------------------------------------------------------------------

def _is_new_ip(user_id: int, ip_address: str) -> bool:
    """True if this IP has never been used by this user before."""
    count = (
        db.session.query(func.count(LoginEvent.id))
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.ip_address == ip_address,
            LoginEvent.success.is_(True),
        )
        .scalar()
    )
    return (count or 0) == 0


def _is_new_user_agent(user_id: int, user_agent: str) -> bool:
    """True if this user agent has never been seen for this user."""
    count = (
        db.session.query(func.count(LoginEvent.id))
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.user_agent == user_agent,
            LoginEvent.success.is_(True),
        )
        .scalar()
    )
    return (count or 0) == 0


def _has_rapid_failures(user_id: int) -> bool:
    """True if there are too many failed attempts in the recent window."""
    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_ATTEMPT_WINDOW_MINUTES)
    count = (
        db.session.query(func.count(LoginEvent.id))
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(False),
            LoginEvent.created_at >= cutoff,
        )
        .scalar()
    )
    return (count or 0) >= FAILED_ATTEMPT_THRESHOLD


def _is_inactive_user(user_id: int) -> bool:
    """True if the user has not logged in for INACTIVITY_DAYS."""
    cutoff = datetime.utcnow() - timedelta(days=INACTIVITY_DAYS)
    last_login = (
        db.session.query(func.max(LoginEvent.created_at))
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(True),
        )
        .scalar()
    )
    if last_login is None:
        return False  # First login ever — not anomalous
    return last_login < cutoff
