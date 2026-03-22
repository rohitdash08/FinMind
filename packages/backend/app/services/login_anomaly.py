"""Login anomaly detection service.

Detects suspicious login behaviour by analysing historical login events for
the same user. Each check returns an anomaly score (0.0 – 1.0) together with
human-readable reasons. When the score exceeds the configured threshold a
``LoginAlert`` is persisted so downstream consumers (email, push, dashboard)
can notify the user.

Heuristics
----------
* **New IP address** – IP has never been seen for this user.
* **New country / city** – Geo location changed since last login.
* **Rapid logins** – Multiple logins within a short window.
* **Failed-login spike** – Several consecutive failures before success.
* **Unusual hour** – Login at an hour the user has never been active.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Tuple

from ..extensions import db
from ..models import LoginAlert, LoginEvent

logger = logging.getLogger("finmind.login_anomaly")

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
ALERT_THRESHOLD = 0.4  # score >= this triggers an alert
RAPID_WINDOW_MINUTES = 5
RAPID_COUNT = 5
FAILED_SPIKE_WINDOW_MINUTES = 30
FAILED_SPIKE_COUNT = 3
HISTORY_DAYS = 90


def analyse_login(
    user_id: int,
    ip_address: str,
    user_agent: str | None = None,
    country: str | None = None,
    city: str | None = None,
    success: bool = True,
    now: datetime | None = None,
) -> Tuple[float, List[str], LoginEvent]:
    """Analyse a login event and return ``(score, reasons, event)``.

    The ``LoginEvent`` is persisted to the database. If the score meets
    the alert threshold a ``LoginAlert`` row is also created.
    """
    now = now or datetime.utcnow()
    reasons: List[str] = []
    score = 0.0

    cutoff = now - timedelta(days=HISTORY_DAYS)
    history: List[LoginEvent] = (
        LoginEvent.query.filter(
            LoginEvent.user_id == user_id,
            LoginEvent.created_at >= cutoff,
        )
        .order_by(LoginEvent.created_at.desc())
        .all()
    )

    # --- New IP ---
    known_ips = {e.ip_address for e in history}
    if ip_address not in known_ips and len(history) > 0:
        score += 0.3
        reasons.append(f"New IP address: {ip_address}")

    # --- New country ---
    if country:
        known_countries = {e.country for e in history if e.country}
        if known_countries and country not in known_countries:
            score += 0.3
            reasons.append(f"New country: {country}")

    # --- New city ---
    if city:
        known_cities = {e.city for e in history if e.city}
        if known_cities and city not in known_cities:
            score += 0.1
            reasons.append(f"New city: {city}")

    # --- Rapid logins ---
    rapid_cutoff = now - timedelta(minutes=RAPID_WINDOW_MINUTES)
    recent = [e for e in history if e.created_at >= rapid_cutoff]
    if len(recent) >= RAPID_COUNT:
        score += 0.2
        reasons.append(
            f"Rapid logins: {len(recent)} attempts in {RAPID_WINDOW_MINUTES} min"
        )

    # --- Failed-login spike ---
    fail_cutoff = now - timedelta(minutes=FAILED_SPIKE_WINDOW_MINUTES)
    recent_failures = [
        e for e in history if not e.success and e.created_at >= fail_cutoff
    ]
    if len(recent_failures) >= FAILED_SPIKE_COUNT:
        score += 0.25
        reasons.append(
            f"Failed-login spike: {len(recent_failures)} failures in "
            f"{FAILED_SPIKE_WINDOW_MINUTES} min"
        )

    # --- Unusual hour ---
    if history:
        hour_counts = Counter(e.created_at.hour for e in history if e.success)
        if hour_counts and hour_counts.get(now.hour, 0) == 0:
            score += 0.1
            reasons.append(f"Unusual login hour: {now.hour:02d}:00 UTC")

    score = min(score, 1.0)

    # Persist event
    event = LoginEvent(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        country=country,
        city=city,
        success=success,
        anomaly_score=score,
        anomaly_reasons=json.dumps(reasons) if reasons else None,
        created_at=now,
    )
    db.session.add(event)
    db.session.flush()  # get event.id

    # Create alert if threshold exceeded
    if score >= ALERT_THRESHOLD and reasons:
        alert_type = _primary_alert_type(reasons)
        alert = LoginAlert(
            user_id=user_id,
            login_event_id=event.id,
            alert_type=alert_type,
            message="; ".join(reasons),
            created_at=now,
        )
        db.session.add(alert)
        logger.warning(
            "Login anomaly detected user_id=%s score=%.2f reasons=%s",
            user_id,
            score,
            reasons,
        )

    return score, reasons, event


def get_user_alerts(
    user_id: int, unacknowledged_only: bool = False, limit: int = 50
) -> List[LoginAlert]:
    """Return recent alerts for a user."""
    q = LoginAlert.query.filter_by(user_id=user_id)
    if unacknowledged_only:
        q = q.filter_by(acknowledged=False)
    return q.order_by(LoginAlert.created_at.desc()).limit(limit).all()


def acknowledge_alert(alert_id: int, user_id: int) -> LoginAlert | None:
    """Mark an alert as acknowledged. Returns ``None`` if not found."""
    alert = LoginAlert.query.filter_by(id=alert_id, user_id=user_id).first()
    if alert:
        alert.acknowledged = True
    return alert


def get_login_history(user_id: int, limit: int = 50) -> List[LoginEvent]:
    """Return recent login events for a user."""
    return (
        LoginEvent.query.filter_by(user_id=user_id)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _primary_alert_type(reasons: List[str]) -> str:
    """Derive the most important alert type from reasons list."""
    text = " ".join(reasons).lower()
    if "new country" in text:
        return "NEW_COUNTRY"
    if "new ip" in text:
        return "NEW_IP"
    if "rapid" in text:
        return "RAPID_LOGIN"
    if "failed" in text:
        return "FAILED_SPIKE"
    if "unusual" in text:
        return "UNUSUAL_HOUR"
    return "SUSPICIOUS"
