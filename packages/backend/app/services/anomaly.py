"""Login anomaly detection service for FinMind.

Tracks login attempts per user and flags suspicious patterns
such as brute-force attempts, impossible travel, and unusual locations.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..extensions import redis_client

logger = logging.getLogger("finmind.anomaly")

LOGIN_PREFIX = "finmind:anomaly:logins:"
ALERT_PREFIX = "finmind:anomaly:alerts:"

# Thresholds
MAX_FAILED_PER_HOUR = 10
MAX_FAILED_PER_DAY = 30
IMPOSSIBLE_TRAVEL_MINUTES = 30  # login from 2 locations within X mins
ALERT_TTL_DAYS = 30


@dataclass
class LoginEvent:
    timestamp: str
    ip: str
    success: bool
    user_agent: str = ""
    country: str = ""
    city: str = ""


@dataclass
class AnomalyAlert:
    user_id: int
    alert_type: str  # brute_force, impossible_travel, unusual_location
    severity: str  # low, medium, high
    details: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return asdict(self)


def _key_login_history(user_id: int) -> str:
    return f"{LOGIN_PREFIX}{user_id}"


def _key_alerts(user_id: int) -> str:
    return f"{ALERT_PREFIX}{user_id}"


def record_login_attempt(
    user_id: int,
    ip: str,
    success: bool,
    user_agent: str = "",
    country: str = "",
    city: str = "",
) -> list[AnomalyAlert]:
    """Record a login attempt and run anomaly detection.

    Returns a list of any alerts generated.
    """
    now = datetime.now(timezone.utc)
    event = LoginEvent(
        timestamp=now.isoformat(),
        ip=ip,
        success=success,
        user_agent=user_agent,
        country=country,
        city=city,
    )

    # Store event (keep last 100 per user)
    key = _key_login_history(user_id)
    redis_client.lpush(key, json.dumps(asdict(event)))
    redis_client.ltrim(key, 0, 99)
    redis_client.expire(key, 86400 * 7)  # 7 days TTL

    # Run anomaly checks
    alerts = []
    alerts.extend(_check_brute_force(user_id, now))
    if success and (country or city):
        alerts.extend(_check_impossible_travel(user_id, now, ip, country, city))

    # Store alerts
    if alerts:
        alert_key = _key_alerts(user_id)
        for alert in alerts:
            redis_client.lpush(alert_key, json.dumps(alert.to_dict()))
        redis_client.ltrim(alert_key, 0, 49)
        redis_client.expire(alert_key, 86400 * ALERT_TTL_DAYS)

        for a in alerts:
            logger.warning(
                "Anomaly alert user=%s type=%s severity=%s",
                user_id, a.alert_type, a.severity,
            )

    return alerts


def _check_brute_force(user_id: int, now: datetime) -> list[AnomalyAlert]:
    """Detect brute-force login attempts."""
    alerts = []
    key = _key_login_history(user_id)
    raw_events = redis_client.lrange(key, 0, 99)

    events = [json.loads(r) for r in raw_events]
    failed = [e for e in events if not e.get("success")]

    # Check hourly failures
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    recent_failed = [e for e in failed if e["timestamp"] >= one_hour_ago]

    if len(recent_failed) >= MAX_FAILED_PER_HOUR:
        alerts.append(AnomalyAlert(
            user_id=user_id,
            alert_type="brute_force",
            severity="high",
            details={
                "failed_attempts_hour": len(recent_failed),
                "threshold": MAX_FAILED_PER_HOUR,
                "message": f"{len(recent_failed)} failed login attempts in the last hour",
            },
        ))
    elif len(recent_failed) >= MAX_FAILED_PER_HOUR // 2:
        alerts.append(AnomalyAlert(
            user_id=user_id,
            alert_type="brute_force",
            severity="medium",
            details={
                "failed_attempts_hour": len(recent_failed),
                "threshold": MAX_FAILED_PER_HOUR,
                "message": f"{len(recent_failed)} failed login attempts in the last hour",
            },
        ))

    # Check daily failures
    one_day_ago = (now - timedelta(days=1)).isoformat()
    daily_failed = [e for e in failed if e["timestamp"] >= one_day_ago]
    if len(daily_failed) >= MAX_FAILED_PER_DAY:
        alerts.append(AnomalyAlert(
            user_id=user_id,
            alert_type="brute_force",
            severity="critical",
            details={
                "failed_attempts_day": len(daily_failed),
                "threshold": MAX_FAILED_PER_DAY,
                "message": f"{len(daily_failed)} failed login attempts in the last 24 hours",
            },
        ))

    return alerts


def _check_impossible_travel(
    user_id: int, now: datetime, ip: str, country: str, city: str
) -> list[AnomalyAlert]:
    """Detect impossible travel (logins from distant locations in short time)."""
    alerts = []
    key = _key_login_history(user_id)
    raw_events = redis_client.lrange(key, 0, 99)

    successful = []
    for r in raw_events:
        e = json.loads(r)
        if e.get("success") and e.get("country"):
            successful.append(e)

    if not successful:
        return alerts

    # Check last successful login location
    last = successful[0]  # Most recent (lpush)
    last_country = last.get("country", "")
    last_city = last.get("city", "")

    if last_country and country and last_country != country:
        last_time = datetime.fromisoformat(last["timestamp"])
        diff_minutes = (now - last_time).total_seconds() / 60
        if diff_minutes < IMPOSSIBLE_TRAVEL_MINUTES:
            alerts.append(AnomalyAlert(
                user_id=user_id,
                alert_type="impossible_travel",
                severity="high",
                details={
                    "previous_location": f"{last_city}, {last_country}",
                    "current_location": f"{city}, {country}",
                    "time_diff_minutes": round(diff_minutes, 1),
                    "message": f"Login from {city}, {country} within {diff_minutes:.0f} minutes of login from {last_city}, {last_country}",
                },
            ))

    return alerts


def get_alerts(user_id: int, limit: int = 20) -> list[dict]:
    """Get anomaly alerts for a user."""
    key = _key_alerts(user_id)
    raw = redis_client.lrange(key, 0, limit - 1)
    return [json.loads(r) for r in raw]


def should_block_login(user_id: int) -> bool:
    """Check if login should be temporarily blocked due to anomalies."""
    key = _key_alerts(user_id)
    recent = redis_client.lrange(key, 0, 4)  # Last 5 alerts
    for r in recent:
        alert = json.loads(r)
        if alert.get("alert_type") == "brute_force" and alert.get("severity") == "critical":
            return True
    return False


def clear_alerts(user_id: int) -> int:
    """Clear all alerts for a user. Returns count cleared."""
    key = _key_alerts(user_id)
    count = redis_client.llen(key)
    redis_client.delete(key)
    return count
