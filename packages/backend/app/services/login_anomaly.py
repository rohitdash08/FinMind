"""Login anomaly detection service.

Detects suspicious login behavior including:
- Multiple failed attempts (brute force)
- New IP addresses
- Unusual login times
- New devices/user agents
- Rapid successive logins from different locations
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy import func, and_
from ..extensions import db, redis_client
from ..models import User, LoginAttempt, LoginAnomaly, AnomalyType, AnomalySeverity
import logging
import hashlib
import json

logger = logging.getLogger("finmind.login_anomaly")

# Configuration constants
FAILED_ATTEMPT_THRESHOLD = 5  # Failed attempts before triggering alert
FAILED_ATTEMPT_WINDOW_MINUTES = 15  # Time window for counting failed attempts
NEW_IP_ALERT_ENABLED = True  # Alert on new IP addresses
UNUSUAL_TIME_START = 2  # 2 AM
UNUSUAL_TIME_END = 5  # 5 AM
RAPID_LOGIN_THRESHOLD_MINUTES = 5  # Time window for rapid login detection
LOCKOUT_THRESHOLD = 10  # Failed attempts before temporary lockout
LOCKOUT_DURATION_MINUTES = 30


def get_device_fingerprint(user_agent: str) -> str:
    """Generate a fingerprint for device identification."""
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


def record_login_attempt(
    user_id: Optional[int],
    email: str,
    ip_address: str,
    user_agent: str,
    success: bool,
    location: Optional[str] = None,
) -> LoginAttempt:
    """Record a login attempt and check for anomalies."""
    device_fingerprint = get_device_fingerprint(user_agent)
    
    attempt = LoginAttempt(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        device_fingerprint=device_fingerprint,
        location=location,
        success=success,
        created_at=datetime.utcnow(),
    )
    db.session.add(attempt)
    db.session.commit()
    
    # Run anomaly detection
    if user_id:
        detect_anomalies(user_id, attempt)
    elif not success:
        # Track failed attempts for unknown users (potential attack)
        detect_brute_force_by_email(email, ip_address)
    
    logger.info(
        "Login attempt recorded: user_id=%s email=%s ip=%s success=%s",
        user_id, email, ip_address, success
    )
    return attempt


def detect_anomalies(user_id: int, current_attempt: LoginAttempt) -> List[LoginAnomaly]:
    """Detect various login anomalies for a user."""
    anomalies = []
    
    if current_attempt.success:
        # Only check these for successful logins
        anomaly = detect_new_ip(user_id, current_attempt)
        if anomaly:
            anomalies.append(anomaly)
        
        anomaly = detect_new_device(user_id, current_attempt)
        if anomaly:
            anomalies.append(anomaly)
        
        anomaly = detect_unusual_time(user_id, current_attempt)
        if anomaly:
            anomalies.append(anomaly)
        
        anomaly = detect_rapid_location_change(user_id, current_attempt)
        if anomaly:
            anomalies.append(anomaly)
    else:
        # Check failed attempt patterns
        anomaly = detect_brute_force(user_id, current_attempt)
        if anomaly:
            anomalies.append(anomaly)
    
    return anomalies


def detect_new_ip(user_id: int, attempt: LoginAttempt) -> Optional[LoginAnomaly]:
    """Detect login from a new IP address."""
    if not NEW_IP_ALERT_ENABLED:
        return None
    
    # Check if this IP has been used before for successful logins
    prior_login = db.session.query(LoginAttempt).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.ip_address == attempt.ip_address,
        LoginAttempt.success == True,
        LoginAttempt.id != attempt.id,
    ).first()
    
    if prior_login:
        return None  # Known IP
    
    # Count total successful logins to avoid alerting on first login
    login_count = db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == True,
    ).scalar()
    
    if login_count <= 1:
        return None  # First login, don't alert
    
    anomaly = LoginAnomaly(
        user_id=user_id,
        login_attempt_id=attempt.id,
        anomaly_type=AnomalyType.NEW_IP,
        severity=AnomalySeverity.MEDIUM,
        description=f"Login from new IP address: {attempt.ip_address}",
        details=json.dumps({"ip_address": attempt.ip_address}),
    )
    db.session.add(anomaly)
    db.session.commit()
    
    logger.warning("New IP detected for user_id=%s: %s", user_id, attempt.ip_address)
    return anomaly


def detect_new_device(user_id: int, attempt: LoginAttempt) -> Optional[LoginAnomaly]:
    """Detect login from a new device."""
    # Check if this device fingerprint has been used before
    prior_login = db.session.query(LoginAttempt).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.device_fingerprint == attempt.device_fingerprint,
        LoginAttempt.success == True,
        LoginAttempt.id != attempt.id,
    ).first()
    
    if prior_login:
        return None  # Known device
    
    # Count total successful logins
    login_count = db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == True,
    ).scalar()
    
    if login_count <= 1:
        return None  # First login
    
    anomaly = LoginAnomaly(
        user_id=user_id,
        login_attempt_id=attempt.id,
        anomaly_type=AnomalyType.NEW_DEVICE,
        severity=AnomalySeverity.MEDIUM,
        description=f"Login from new device",
        details=json.dumps({
            "device_fingerprint": attempt.device_fingerprint,
            "user_agent": attempt.user_agent,
        }),
    )
    db.session.add(anomaly)
    db.session.commit()
    
    logger.warning("New device detected for user_id=%s", user_id)
    return anomaly


def detect_unusual_time(user_id: int, attempt: LoginAttempt) -> Optional[LoginAnomaly]:
    """Detect login at unusual hours."""
    hour = attempt.created_at.hour
    
    if not (UNUSUAL_TIME_START <= hour < UNUSUAL_TIME_END):
        return None  # Normal hours
    
    # Check if user typically logs in at this hour
    similar_hour_logins = db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == True,
        LoginAttempt.id != attempt.id,
        func.extract('hour', LoginAttempt.created_at).between(
            UNUSUAL_TIME_START, UNUSUAL_TIME_END - 1
        ),
    ).scalar()
    
    if similar_hour_logins >= 3:
        return None  # User regularly logs in at this hour
    
    anomaly = LoginAnomaly(
        user_id=user_id,
        login_attempt_id=attempt.id,
        anomaly_type=AnomalyType.UNUSUAL_TIME,
        severity=AnomalySeverity.LOW,
        description=f"Login at unusual hour: {hour:02d}:00",
        details=json.dumps({"hour": hour}),
    )
    db.session.add(anomaly)
    db.session.commit()
    
    logger.info("Unusual time login for user_id=%s at hour=%d", user_id, hour)
    return anomaly


def detect_rapid_location_change(user_id: int, attempt: LoginAttempt) -> Optional[LoginAnomaly]:
    """Detect impossible travel - rapid login from different IPs."""
    cutoff = datetime.utcnow() - timedelta(minutes=RAPID_LOGIN_THRESHOLD_MINUTES)
    
    recent_logins = db.session.query(LoginAttempt).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == True,
        LoginAttempt.id != attempt.id,
        LoginAttempt.created_at >= cutoff,
        LoginAttempt.ip_address != attempt.ip_address,
    ).all()
    
    if not recent_logins:
        return None
    
    anomaly = LoginAnomaly(
        user_id=user_id,
        login_attempt_id=attempt.id,
        anomaly_type=AnomalyType.IMPOSSIBLE_TRAVEL,
        severity=AnomalySeverity.HIGH,
        description="Rapid login from different IP addresses (possible credential sharing or theft)",
        details=json.dumps({
            "current_ip": attempt.ip_address,
            "previous_ips": [l.ip_address for l in recent_logins],
            "time_window_minutes": RAPID_LOGIN_THRESHOLD_MINUTES,
        }),
    )
    db.session.add(anomaly)
    db.session.commit()
    
    logger.warning(
        "Impossible travel detected for user_id=%s: rapid IP change",
        user_id
    )
    return anomaly


def detect_brute_force(user_id: int, attempt: LoginAttempt) -> Optional[LoginAnomaly]:
    """Detect brute force attempts on a user account."""
    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_ATTEMPT_WINDOW_MINUTES)
    
    failed_count = db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == False,
        LoginAttempt.created_at >= cutoff,
    ).scalar()
    
    if failed_count < FAILED_ATTEMPT_THRESHOLD:
        return None
    
    # Check if we already have an unresolved brute force alert
    existing = db.session.query(LoginAnomaly).filter(
        LoginAnomaly.user_id == user_id,
        LoginAnomaly.anomaly_type == AnomalyType.BRUTE_FORCE,
        LoginAnomaly.resolved == False,
        LoginAnomaly.created_at >= cutoff,
    ).first()
    
    if existing:
        return None  # Already alerted
    
    severity = AnomalySeverity.HIGH if failed_count >= LOCKOUT_THRESHOLD else AnomalySeverity.MEDIUM
    
    anomaly = LoginAnomaly(
        user_id=user_id,
        login_attempt_id=attempt.id,
        anomaly_type=AnomalyType.BRUTE_FORCE,
        severity=severity,
        description=f"Multiple failed login attempts: {failed_count} in {FAILED_ATTEMPT_WINDOW_MINUTES} minutes",
        details=json.dumps({
            "failed_count": failed_count,
            "window_minutes": FAILED_ATTEMPT_WINDOW_MINUTES,
            "ip_address": attempt.ip_address,
        }),
    )
    db.session.add(anomaly)
    db.session.commit()
    
    # Set lockout if threshold exceeded
    if failed_count >= LOCKOUT_THRESHOLD:
        set_account_lockout(user_id)
    
    logger.warning(
        "Brute force detected for user_id=%s: %d failed attempts",
        user_id, failed_count
    )
    return anomaly


def detect_brute_force_by_email(email: str, ip_address: str):
    """Track failed attempts for non-existent users."""
    key = f"failed_login:{email}"
    count = redis_client.incr(key)
    redis_client.expire(key, FAILED_ATTEMPT_WINDOW_MINUTES * 60)
    
    if count >= FAILED_ATTEMPT_THRESHOLD:
        logger.warning(
            "Multiple failed logins for unknown email=%s from ip=%s",
            email, ip_address
        )


def set_account_lockout(user_id: int):
    """Temporarily lock an account after too many failed attempts."""
    key = f"account_lockout:{user_id}"
    redis_client.setex(key, LOCKOUT_DURATION_MINUTES * 60, "1")
    logger.warning("Account locked for user_id=%s for %d minutes", user_id, LOCKOUT_DURATION_MINUTES)


def is_account_locked(user_id: int) -> bool:
    """Check if an account is currently locked."""
    key = f"account_lockout:{user_id}"
    return redis_client.exists(key) > 0


def get_lockout_remaining(user_id: int) -> Optional[int]:
    """Get remaining lockout time in seconds."""
    key = f"account_lockout:{user_id}"
    ttl = redis_client.ttl(key)
    return ttl if ttl > 0 else None


def clear_account_lockout(user_id: int):
    """Clear account lockout (admin action)."""
    key = f"account_lockout:{user_id}"
    redis_client.delete(key)
    logger.info("Account lockout cleared for user_id=%s", user_id)


def get_user_anomalies(
    user_id: int,
    unresolved_only: bool = False,
    limit: int = 50,
) -> List[LoginAnomaly]:
    """Get login anomalies for a user."""
    query = db.session.query(LoginAnomaly).filter(
        LoginAnomaly.user_id == user_id
    )
    
    if unresolved_only:
        query = query.filter(LoginAnomaly.resolved == False)
    
    return query.order_by(LoginAnomaly.created_at.desc()).limit(limit).all()


def resolve_anomaly(anomaly_id: int, user_id: int, resolution_note: str = None) -> bool:
    """Mark an anomaly as resolved."""
    anomaly = db.session.query(LoginAnomaly).filter(
        LoginAnomaly.id == anomaly_id,
        LoginAnomaly.user_id == user_id,
    ).first()
    
    if not anomaly:
        return False
    
    anomaly.resolved = True
    anomaly.resolved_at = datetime.utcnow()
    if resolution_note:
        details = json.loads(anomaly.details or "{}")
        details["resolution_note"] = resolution_note
        anomaly.details = json.dumps(details)
    
    db.session.commit()
    logger.info("Anomaly %d resolved for user_id=%s", anomaly_id, user_id)
    return True


def get_login_history(user_id: int, limit: int = 50) -> List[LoginAttempt]:
    """Get login history for a user."""
    return db.session.query(LoginAttempt).filter(
        LoginAttempt.user_id == user_id
    ).order_by(LoginAttempt.created_at.desc()).limit(limit).all()


def get_security_summary(user_id: int) -> Dict[str, Any]:
    """Get a security summary for a user."""
    # Count recent anomalies
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    unresolved_anomalies = db.session.query(func.count(LoginAnomaly.id)).filter(
        LoginAnomaly.user_id == user_id,
        LoginAnomaly.resolved == False,
    ).scalar()
    
    recent_anomalies = db.session.query(func.count(LoginAnomaly.id)).filter(
        LoginAnomaly.user_id == user_id,
        LoginAnomaly.created_at >= week_ago,
    ).scalar()
    
    # Count failed logins in last 24h
    day_ago = datetime.utcnow() - timedelta(days=1)
    failed_logins_24h = db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == False,
        LoginAttempt.created_at >= day_ago,
    ).scalar()
    
    # Get unique IPs in last 30 days
    month_ago = datetime.utcnow() - timedelta(days=30)
    unique_ips = db.session.query(func.count(func.distinct(LoginAttempt.ip_address))).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == True,
        LoginAttempt.created_at >= month_ago,
    ).scalar()
    
    # Get last successful login
    last_login = db.session.query(LoginAttempt).filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.success == True,
    ).order_by(LoginAttempt.created_at.desc()).first()
    
    is_locked = is_account_locked(user_id)
    lockout_remaining = get_lockout_remaining(user_id) if is_locked else None
    
    return {
        "unresolved_anomalies": unresolved_anomalies,
        "recent_anomalies_7d": recent_anomalies,
        "failed_logins_24h": failed_logins_24h,
        "unique_ips_30d": unique_ips,
        "last_login": last_login.created_at.isoformat() if last_login else None,
        "last_login_ip": last_login.ip_address if last_login else None,
        "account_locked": is_locked,
        "lockout_remaining_seconds": lockout_remaining,
    }
