"""
Login anomaly detection service.

Detects suspicious login behaviour based on:
- New/unknown IP addresses
- New/unknown user-agent strings (device fingerprint)
- Brute-force: too many failed attempts in a short window
- Unusual hours (2-5 AM UTC)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Tuple

from ..extensions import db
from ..models import LoginEvent

logger = logging.getLogger("finmind.security")

# Tunable thresholds
BRUTE_FORCE_WINDOW_MINUTES = 15
BRUTE_FORCE_THRESHOLD = 5
UNUSUAL_HOUR_START = 2   # 02:00 UTC inclusive
UNUSUAL_HOUR_END = 5     # 04:59 UTC inclusive


def _recent_events(user_id: int, minutes: int) -> List[LoginEvent]:
    """Return login events for *user_id* in the last *minutes*."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.created_at >= cutoff,
        )
        .order_by(LoginEvent.created_at.desc())
        .all()
    )


def _known_ips(user_id: int) -> set[str]:
    rows = (
        db.session.query(LoginEvent.ip_address)
        .filter(LoginEvent.user_id == user_id, LoginEvent.success == True)  # noqa: E712
        .distinct()
        .all()
    )
    return {r.ip_address for r in rows if r.ip_address}


def _known_agents(user_id: int) -> set[str]:
    rows = (
        db.session.query(LoginEvent.user_agent)
        .filter(LoginEvent.user_id == user_id, LoginEvent.success == True)  # noqa: E712
        .distinct()
        .all()
    )
    return {r.user_agent for r in rows if r.user_agent}


def compute_anomaly_score(
    user_id: int,
    ip_address: str,
    user_agent: str,
    success: bool,
    now: datetime | None = None,
) -> Tuple[float, List[str]]:
    """
    Return (score, reasons) where score is in [0.0, 1.0].
    A higher score means the login looks more suspicious.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    score = 0.0
    reasons: List[str] = []

    # 1. New IP address (compared to successful logins)
    known_ips = _known_ips(user_id)
    if known_ips and ip_address and ip_address not in known_ips:
        score += 0.30
        reasons.append("login from new IP address")

    # 2. New device / user-agent
    known_agents = _known_agents(user_id)
    if known_agents and user_agent and user_agent not in known_agents:
        score += 0.25
        reasons.append("login from new device or browser")

    # 3. Brute-force: many failed attempts recently
    recent = _recent_events(user_id, BRUTE_FORCE_WINDOW_MINUTES)
    recent_failures = [e for e in recent if not e.success]
    if len(recent_failures) >= BRUTE_FORCE_THRESHOLD:
        score += 0.40
        reasons.append(
            f"{len(recent_failures)} failed login attempts in the last "
            f"{BRUTE_FORCE_WINDOW_MINUTES} minutes"
        )

    # 4. Unusual hour (2-5 AM UTC)
    hour = now.hour
    if UNUSUAL_HOUR_START <= hour <= UNUSUAL_HOUR_END:
        score += 0.15
        reasons.append(f"login at unusual hour ({hour:02d}:00 UTC)")

    # Clamp to [0, 1]
    score = round(min(score, 1.0), 2)
    return score, reasons


def record_login(
    user_id: int,
    ip_address: str,
    user_agent: str,
    success: bool,
) -> LoginEvent:
    """
    Persist a LoginEvent and annotate it with the anomaly score.
    Returns the saved LoginEvent.
    """
    score, reasons = compute_anomaly_score(user_id, ip_address, user_agent, success)
    event = LoginEvent(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        anomaly_score=score,
        anomaly_reasons=", ".join(reasons) if reasons else None,
    )
    db.session.add(event)
    db.session.commit()

    if score > 0 and success:
        logger.warning(
            "Suspicious login for user_id=%s score=%.2f reasons=%s ip=%s",
            user_id,
            score,
            reasons,
            ip_address,
        )
    return event
