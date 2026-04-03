"""Login anomaly detection service.

Detects suspicious login behaviour and creates alerts:
- BRUTE_FORCE: Many failed attempts in a short window
- NEW_IP: Successful login from an IP never seen for this user
- NEW_DEVICE: Successful login from an unrecognised user-agent
- IMPOSSIBLE_TRAVEL: Two successful logins from different countries within
  a suspiciously short time span
- ODD_HOUR: Login outside the user's typical active hours
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Sequence

from ..extensions import db, redis_client
from ..models import LoginAlert, LoginAttempt

logger = logging.getLogger("finmind.login_anomaly")

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
FAILED_ATTEMPT_WINDOW_MINUTES = 15
FAILED_ATTEMPT_THRESHOLD = 5
LOCKOUT_DURATION_MINUTES = 30
ODD_HOUR_START = 1   # 01:00
ODD_HOUR_END = 5     # 05:00
IMPOSSIBLE_TRAVEL_MINUTES = 60


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def record_login_attempt(
    *,
    email: str,
    ip_address: str,
    user_agent: str | None,
    success: bool,
    user_id: int | None = None,
    country: str | None = None,
) -> LoginAttempt:
    """Persist a login attempt and return the row."""
    attempt = LoginAttempt(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        country=country,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def check_account_locked(email: str) -> bool:
    """Return True if the account is temporarily locked due to brute-force."""
    try:
        key = _lockout_key(email)
        return redis_client.get(key) is not None
    except Exception:
        logger.warning("Redis unavailable for lockout check, allowing login")
        return False


def lock_account(email: str) -> None:
    """Lock an account for LOCKOUT_DURATION_MINUTES."""
    try:
        key = _lockout_key(email)
        redis_client.setex(key, LOCKOUT_DURATION_MINUTES * 60, "1")
        logger.warning("Account locked for email=%s", email)
    except Exception:
        logger.error("Redis unavailable, could not lock account for email=%s", email)


def analyse_login(attempt: LoginAttempt) -> list[LoginAlert]:
    """Run all anomaly detectors against *attempt* and return created alerts."""
    alerts: list[LoginAlert] = []

    if not attempt.success:
        alert = _check_brute_force(attempt)
        if alert:
            alerts.append(alert)
        return alerts

    # Only run these checks on successful logins
    for checker in (_check_new_ip, _check_new_device, _check_odd_hour, _check_impossible_travel):
        alert = checker(attempt)
        if alert:
            alerts.append(alert)

    return alerts


def get_recent_attempts(user_id: int, limit: int = 20) -> Sequence[LoginAttempt]:
    """Return the most recent login attempts for a user."""
    return (
        db.session.query(LoginAttempt)
        .filter_by(user_id=user_id)
        .order_by(LoginAttempt.created_at.desc())
        .limit(limit)
        .all()
    )


def get_alerts(user_id: int, *, include_acknowledged: bool = False) -> Sequence[LoginAlert]:
    """Return alerts for a user, newest first."""
    query = db.session.query(LoginAlert).filter_by(user_id=user_id)
    if not include_acknowledged:
        query = query.filter_by(acknowledged=False)
    return query.order_by(LoginAlert.created_at.desc()).all()


def acknowledge_alert(alert_id: int, user_id: int) -> LoginAlert | None:
    """Mark an alert as acknowledged. Returns None if not found."""
    alert = (
        db.session.query(LoginAlert)
        .filter_by(id=alert_id, user_id=user_id)
        .first()
    )
    if alert is None:
        return None
    alert.acknowledged = True
    db.session.commit()
    return alert


# ---------------------------------------------------------------------------
# Internal checkers
# ---------------------------------------------------------------------------

def _check_brute_force(attempt: LoginAttempt) -> LoginAlert | None:
    """Detect many consecutive failed attempts within a short window."""
    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_ATTEMPT_WINDOW_MINUTES)
    recent_failures = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.email == attempt.email,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
        .count()
    )
    if recent_failures >= FAILED_ATTEMPT_THRESHOLD:
        lock_account(attempt.email)
        return _create_alert(
            user_id=attempt.user_id,
            attempt_id=attempt.id,
            alert_type="BRUTE_FORCE",
            severity="CRITICAL",
            message=(
                f"Possible brute-force attack: {recent_failures} failed login attempts "
                f"from IP {attempt.ip_address} in the last {FAILED_ATTEMPT_WINDOW_MINUTES} minutes. "
                "Account has been temporarily locked."
            ),
            metadata={"failed_count": recent_failures, "ip": attempt.ip_address},
        )
    return None


def _check_new_ip(attempt: LoginAttempt) -> LoginAlert | None:
    """Alert when a user logs in from an IP never seen before."""
    previous = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.user_id == attempt.user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.ip_address == attempt.ip_address,
            LoginAttempt.id != attempt.id,
        )
        .first()
    )
    if previous is None:
        return _create_alert(
            user_id=attempt.user_id,
            attempt_id=attempt.id,
            alert_type="NEW_IP",
            severity="MEDIUM",
            message=f"Login from new IP address: {attempt.ip_address}",
            metadata={"ip": attempt.ip_address},
        )
    return None


def _check_new_device(attempt: LoginAttempt) -> LoginAlert | None:
    """Alert when user-agent has not been seen before for this user."""
    if not attempt.user_agent:
        return None
    previous = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.user_id == attempt.user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.user_agent == attempt.user_agent,
            LoginAttempt.id != attempt.id,
        )
        .first()
    )
    if previous is None:
        return _create_alert(
            user_id=attempt.user_id,
            attempt_id=attempt.id,
            alert_type="NEW_DEVICE",
            severity="MEDIUM",
            message=f"Login from new device: {attempt.user_agent[:80]}",
            metadata={"user_agent": attempt.user_agent},
        )
    return None


def _check_odd_hour(attempt: LoginAttempt) -> LoginAlert | None:
    """Alert when login happens during unusual hours (01:00-05:00 UTC)."""
    hour = attempt.created_at.hour
    if ODD_HOUR_START <= hour < ODD_HOUR_END:
        return _create_alert(
            user_id=attempt.user_id,
            attempt_id=attempt.id,
            alert_type="ODD_HOUR",
            severity="LOW",
            message=f"Login at unusual hour ({hour:02d}:00 UTC)",
            metadata={"hour": hour},
        )
    return None


def _check_impossible_travel(attempt: LoginAttempt) -> LoginAlert | None:
    """Alert when two successful logins from different countries happen too quickly."""
    if not attempt.country:
        return None
    cutoff = datetime.utcnow() - timedelta(minutes=IMPOSSIBLE_TRAVEL_MINUTES)
    previous = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.user_id == attempt.user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.id != attempt.id,
            LoginAttempt.created_at >= cutoff,
            LoginAttempt.country.isnot(None),
            LoginAttempt.country != attempt.country,
        )
        .order_by(LoginAttempt.created_at.desc())
        .first()
    )
    if previous is not None:
        return _create_alert(
            user_id=attempt.user_id,
            attempt_id=attempt.id,
            alert_type="IMPOSSIBLE_TRAVEL",
            severity="HIGH",
            message=(
                f"Successive logins from {previous.country} and {attempt.country} "
                f"within {IMPOSSIBLE_TRAVEL_MINUTES} minutes."
            ),
            metadata={
                "previous_country": previous.country,
                "current_country": attempt.country,
            },
        )
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lockout_key(email: str) -> str:
    return f"auth:lockout:{email}"


def _create_alert(
    *,
    user_id: int | None,
    attempt_id: int | None,
    alert_type: str,
    severity: str,
    message: str,
    metadata: dict | None = None,
) -> LoginAlert:
    alert = LoginAlert(
        user_id=user_id,
        login_attempt_id=attempt_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.session.add(alert)
    db.session.commit()
    logger.info(
        "Login alert created: type=%s severity=%s user_id=%s",
        alert_type,
        severity,
        user_id,
    )
    return alert
