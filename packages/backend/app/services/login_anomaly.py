"""
Login Anomaly Detection Service
================================
Analyses each login event and flags suspicious activity based on:
  1. New IP address  — IP never seen before for this user
  2. New device      — user-agent never seen before for this user
  3. Unusual hour    — login between 01:00 and 05:00 UTC
  4. Rapid attempts  — more than 5 login attempts in a 15-minute window
  5. Geo-location    — resolved via ip-api.com (best-effort, no key required)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from ..extensions import db
from ..models import LoginAlert, LoginEvent

logger = logging.getLogger("finmind.anomaly")

# --------------------------------------------------------------------------- #
# Thresholds (all tuneable via constants)                                      #
# --------------------------------------------------------------------------- #
RAPID_ATTEMPT_WINDOW_MINUTES: int = 15
RAPID_ATTEMPT_THRESHOLD: int = 5
UNUSUAL_HOUR_START: int = 1   # 01:00 UTC (inclusive)
UNUSUAL_HOUR_END: int = 5     # 05:00 UTC (exclusive)
GEO_TIMEOUT_SECONDS: float = 2.0  # keep logins fast


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def record_login(
    *,
    user_id: Optional[int],
    ip_address: Optional[str],
    user_agent: Optional[str],
    success: bool,
) -> LoginEvent:
    """
    Persist a LoginEvent, run anomaly checks, and create LoginAlerts when
    suspicious patterns are detected.  Returns the saved LoginEvent.
    """
    geo = _resolve_geo(ip_address) if ip_address else None

    event = LoginEvent(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        geo_location=geo,
        success=success,
        is_suspicious=False,
        suspicion_reasons=None,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.session.add(event)
    db.session.flush()  # get event.id before further queries

    # Only run anomaly detection when we have a known user
    if user_id is not None:
        reasons = _detect_anomalies(event)
        if reasons:
            event.is_suspicious = True
            event.suspicion_reasons = json.dumps(reasons)
            for reason in reasons:
                _create_alert(event, reason)

    db.session.commit()
    return event


def get_login_history(user_id: int, limit: int = 50) -> list[dict]:
    events = (
        db.session.query(LoginEvent)
        .filter_by(user_id=user_id)
        .order_by(LoginEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [e.to_dict() for e in events]


def get_alerts(user_id: int, include_acknowledged: bool = False) -> list[dict]:
    q = db.session.query(LoginAlert).filter_by(user_id=user_id)
    if not include_acknowledged:
        q = q.filter_by(acknowledged=False)
    alerts = q.order_by(LoginAlert.created_at.desc()).all()
    return [a.to_dict() for a in alerts]


def acknowledge_alert(alert_id: int, user_id: int) -> Optional[dict]:
    alert = db.session.get(LoginAlert, alert_id)
    if not alert or alert.user_id != user_id:
        return None
    alert.acknowledged = True
    db.session.commit()
    return alert.to_dict()


# --------------------------------------------------------------------------- #
# Admin helpers                                                                #
# --------------------------------------------------------------------------- #

def admin_get_all_events(limit: int = 100, offset: int = 0) -> list[dict]:
    events = (
        db.session.query(LoginEvent)
        .order_by(LoginEvent.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [e.to_dict() for e in events]


def admin_get_all_alerts(limit: int = 100, offset: int = 0) -> list[dict]:
    alerts = (
        db.session.query(LoginAlert)
        .order_by(LoginAlert.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [a.to_dict() for a in alerts]


# --------------------------------------------------------------------------- #
# Internal detection logic                                                     #
# --------------------------------------------------------------------------- #

def _detect_anomalies(event: LoginEvent) -> list[str]:
    reasons: list[str] = []

    if _is_new_ip(event):
        reasons.append("new_ip")
    if _is_new_device(event):
        reasons.append("new_device")
    if _is_unusual_hour(event):
        reasons.append("unusual_hour")
    if _is_rapid_attempt(event):
        reasons.append("rapid_attempts")

    return reasons


def _is_new_ip(event: LoginEvent) -> bool:
    if not event.ip_address:
        return False
    prior = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == event.user_id,
            LoginEvent.ip_address == event.ip_address,
            LoginEvent.id != event.id,
        )
        .first()
    )
    return prior is None


def _is_new_device(event: LoginEvent) -> bool:
    if not event.user_agent:
        return False
    prior = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == event.user_id,
            LoginEvent.user_agent == event.user_agent,
            LoginEvent.id != event.id,
        )
        .first()
    )
    return prior is None


def _is_unusual_hour(event: LoginEvent) -> bool:
    hour = event.timestamp.hour  # already stored as UTC
    return UNUSUAL_HOUR_START <= hour < UNUSUAL_HOUR_END


def _is_rapid_attempt(event: LoginEvent) -> bool:
    window_start = event.timestamp - timedelta(minutes=RAPID_ATTEMPT_WINDOW_MINUTES)
    count = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.user_id == event.user_id,
            LoginEvent.timestamp >= window_start,
            LoginEvent.timestamp <= event.timestamp,
        )
        .count()
    )
    return count > RAPID_ATTEMPT_THRESHOLD


# --------------------------------------------------------------------------- #
# Alert creation                                                               #
# --------------------------------------------------------------------------- #

_ALERT_MESSAGES: dict[str, str] = {
    "new_ip": "Login detected from a new IP address: {ip}",
    "new_device": "Login detected from an unrecognised device.",
    "unusual_hour": "Login detected at an unusual hour ({hour}:00 UTC).",
    "rapid_attempts": (
        f"More than {RAPID_ATTEMPT_THRESHOLD} login attempts detected "
        f"within {RAPID_ATTEMPT_WINDOW_MINUTES} minutes — possible brute-force attack."
    ),
}


def _create_alert(event: LoginEvent, reason: str) -> None:
    template = _ALERT_MESSAGES.get(reason, "Suspicious login activity detected.")
    message = template.format(
        ip=event.ip_address or "unknown",
        hour=event.timestamp.hour,
    )
    alert = LoginAlert(
        user_id=event.user_id,
        login_event_id=event.id,
        alert_type=reason,
        message=message,
    )
    db.session.add(alert)


# --------------------------------------------------------------------------- #
# Geo-location (best-effort)                                                   #
# --------------------------------------------------------------------------- #

def _resolve_geo(ip: str) -> Optional[str]:
    """
    Resolve a human-readable location string from an IP address using the
    free ip-api.com endpoint.  Returns None on any failure.
    """
    # Skip private / loopback ranges to avoid useless external calls
    if ip in ("127.0.0.1", "::1") or ip.startswith(("10.", "192.168.", "172.")):
        return "localhost"
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,city,country"},
            timeout=GEO_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if data.get("status") == "success":
            city = data.get("city", "")
            country = data.get("country", "")
            return f"{city}, {country}".strip(", ") or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Geo-lookup failed for %s: %s", ip, exc)
    return None
