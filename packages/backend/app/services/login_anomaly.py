"""Login anomaly detection service.

Detects suspicious login patterns and generates alerts:
- Rapid failed login attempts (brute force)
- Logins from new IP addresses
- Logins from new devices (user agent)
- Unusual login time patterns
- Multiple failed attempts followed by success (credential stuffing)
"""

import json
import hashlib
from datetime import datetime, timedelta
from collections import Counter

from ..extensions import db, redis_client
from ..models import LoginAttempt, LoginAlert, User

# Detection thresholds
BRUTE_FORCE_WINDOW_MINUTES = 15
BRUTE_FORCE_THRESHOLD = 5
NEW_IP_LOOKBACK_DAYS = 30
NEW_DEVICE_LOOKBACK_DAYS = 90
CREDENTIAL_STUFFING_WINDOW_MINUTES = 30
CREDENTIAL_STUFFING_THRESHOLD = 3


def _hash_ua(user_agent: str | None) -> str:
    """Hash user agent to a short fingerprint for comparison."""
    if not user_agent:
        return "unknown"
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


def record_login_attempt(
    email: str,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    failure_reason: str | None = None,
) -> LoginAttempt:
    """Record a login attempt and return the created record."""
    user = db.session.query(User).filter_by(email=email).first()
    attempt = LoginAttempt(
        user_id=user.id if user else None,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        failure_reason=failure_reason,
    )
    db.session.add(attempt)
    db.session.commit()

    # Cache recent attempt count in Redis for fast brute-force detection
    if not success:
        key = f"login:fail:{email}"
        try:
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, BRUTE_FORCE_WINDOW_MINUTES * 60)
            pipe.execute()
        except Exception:
            pass

    return attempt


def detect_anomalies(attempt: LoginAttempt) -> list[LoginAlert]:
    """Run all anomaly checks on a login attempt. Returns new alerts created."""
    alerts = []

    if attempt.success and attempt.user_id:
        alerts.extend(_detect_new_ip(attempt))
        alerts.extend(_detect_new_device(attempt))
        alerts.extend(_detect_credential_stuffing(attempt))

    if not attempt.success:
        alerts.extend(_detect_brute_force(attempt))

    for alert in alerts:
        db.session.add(alert)
    if alerts:
        db.session.commit()

    return alerts


def _detect_brute_force(attempt: LoginAttempt) -> list[LoginAlert]:
    """Detect rapid failed login attempts (brute force)."""
    alerts = []
    # Use Redis counter for speed
    key = f"login:fail:{attempt.email}"
    try:
        count = int(redis_client.get(key) or 0)
    except Exception:
        # Fallback to DB query
        window = datetime.utcnow() - timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES)
        count = (
            db.session.query(LoginAttempt)
            .filter(
                LoginAttempt.email == attempt.email,
                LoginAttempt.success.is_(False),
                LoginAttempt.created_at >= window,
            )
            .count()
        )

    if count >= BRUTE_FORCE_THRESHOLD:
        user = db.session.query(User).filter_by(email=attempt.email).first()
        if user:
            alert = LoginAlert(
                user_id=user.id,
                alert_type="brute_force",
                severity="high",
                message=f"{count} failed login attempts in the last {BRUTE_FORCE_WINDOW_MINUTES} minutes",
                metadata_json=json.dumps(
                    {
                        "failed_count": count,
                        "window_minutes": BRUTE_FORCE_WINDOW_MINUTES,
                        "ip_address": attempt.ip_address,
                    }
                ),
            )
            alerts.append(alert)
    return alerts


def _detect_new_ip(attempt: LoginAttempt) -> list[LoginAlert]:
    """Detect login from a previously unseen IP address."""
    alerts = []
    if not attempt.ip_address or not attempt.user_id:
        return alerts

    cutoff = datetime.utcnow() - timedelta(days=NEW_IP_LOOKBACK_DAYS)
    known_ips = (
        db.session.query(LoginAttempt.ip_address)
        .filter(
            LoginAttempt.user_id == attempt.user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.created_at >= cutoff,
            LoginAttempt.id != attempt.id,
        )
        .distinct()
        .all()
    )
    known_ip_set = {row[0] for row in known_ips}

    if attempt.ip_address not in known_ip_set and len(known_ip_set) > 0:
        alert = LoginAlert(
            user_id=attempt.user_id,
            alert_type="new_ip",
            severity="medium",
            message=f"Login from new IP address: {attempt.ip_address}",
            metadata_json=json.dumps(
                {
                    "new_ip": attempt.ip_address,
                    "known_ips_count": len(known_ip_set),
                }
            ),
        )
        alerts.append(alert)
    return alerts


def _detect_new_device(attempt: LoginAttempt) -> list[LoginAlert]:
    """Detect login from a previously unseen device (user agent)."""
    alerts = []
    if not attempt.user_agent or not attempt.user_id:
        return alerts

    current_ua_hash = _hash_ua(attempt.user_agent)
    cutoff = datetime.utcnow() - timedelta(days=NEW_DEVICE_LOOKBACK_DAYS)

    past_attempts = (
        db.session.query(LoginAttempt.user_agent)
        .filter(
            LoginAttempt.user_id == attempt.user_id,
            LoginAttempt.success.is_(True),
            LoginAttempt.created_at >= cutoff,
            LoginAttempt.user_agent.isnot(None),
            LoginAttempt.id != attempt.id,
        )
        .distinct()
        .all()
    )
    known_ua_hashes = {_hash_ua(row[0]) for row in past_attempts}

    if current_ua_hash not in known_ua_hashes and len(known_ua_hashes) > 0:
        alert = LoginAlert(
            user_id=attempt.user_id,
            alert_type="new_device",
            severity="medium",
            message="Login from a new device",
            metadata_json=json.dumps(
                {
                    "user_agent": attempt.user_agent[:200],
                    "known_devices_count": len(known_ua_hashes),
                }
            ),
        )
        alerts.append(alert)
    return alerts


def _detect_credential_stuffing(attempt: LoginAttempt) -> list[LoginAlert]:
    """Detect multiple failed attempts followed by success (credential stuffing pattern)."""
    alerts = []
    if not attempt.user_id:
        return alerts

    window = datetime.utcnow() - timedelta(minutes=CREDENTIAL_STUFFING_WINDOW_MINUTES)
    recent_failures = (
        db.session.query(LoginAttempt)
        .filter(
            LoginAttempt.user_id == attempt.user_id,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= window,
            LoginAttempt.id != attempt.id,
        )
        .count()
    )

    if recent_failures >= CREDENTIAL_STUFFING_THRESHOLD:
        alert = LoginAlert(
            user_id=attempt.user_id,
            alert_type="credential_stuffing",
            severity="high",
            message=f"Successful login after {recent_failures} failed attempts — possible credential stuffing",
            metadata_json=json.dumps(
                {
                    "prior_failures": recent_failures,
                    "window_minutes": CREDENTIAL_STUFFING_WINDOW_MINUTES,
                    "ip_address": attempt.ip_address,
                }
            ),
        )
        alerts.append(alert)
    return alerts


def get_user_alerts(
    user_id: int, unread_only: bool = False, limit: int = 50
) -> list[LoginAlert]:
    """Retrieve login alerts for a user."""
    query = db.session.query(LoginAlert).filter_by(user_id=user_id)
    if unread_only:
        query = query.filter_by(read=False)
    return query.order_by(LoginAlert.created_at.desc()).limit(limit).all()


def mark_alerts_read(user_id: int, alert_ids: list[int] | None = None) -> int:
    """Mark alerts as read. If alert_ids is None, mark all unread."""
    query = db.session.query(LoginAlert).filter_by(user_id=user_id, read=False)
    if alert_ids:
        query = query.filter(LoginAlert.id.in_(alert_ids))
    count = query.update({"read": True}, synchronize_session=False)
    db.session.commit()
    return count
