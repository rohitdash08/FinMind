"""
Login Anomaly Detection Service

Provides real-time detection of suspicious login activities including:
- New IP address detection
- New device detection
- Unusual login time detection
- Brute force attack detection
- Geographic anomaly detection

Risk scores are calculated based on multiple signals and security alerts
are automatically generated when thresholds are exceeded.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from flask import request
from sqlalchemy import func, desc, and_, or_
from ..extensions import db, redis_client
from ..models import LoginEvent, SecurityAlert, User, AuditLog, LoginEventType, AlertSeverity, AlertStatus

logger = logging.getLogger("finmind.security")


# Risk score thresholds
RISK_THRESHOLD_LOW = 0.3
RISK_THRESHOLD_MEDIUM = 0.5
RISK_THRESHOLD_HIGH = 0.7
RISK_THRESHOLD_CRITICAL = 0.9

# Brute force detection settings
BRUTE_FORCE_THRESHOLD = 5  # Max failed attempts before blocking
BRUTE_FORCE_WINDOW_MINUTES = 15  # Time window for counting attempts
BRUTE_FORCE_BLOCK_MINUTES = 30  # How long to block after threshold reached

# Redis key prefixes
REDIS_PREFIX = "security:"
BRUTE_FORCE_KEY = REDIS_PREFIX + "brute_force:{ip}"
USER_IPS_KEY = REDIS_PREFIX + "user_ips:{user_id}"
USER_DEVICES_KEY = REDIS_PREFIX + "user_devices:{user_id}"


class AnomalyDetectionError(Exception):
    """Base exception for anomaly detection errors."""
    pass


def get_client_ip() -> Optional[str]:
    """Extract client IP address from request."""
    # Check for proxy headers first
    if request:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.remote_addr
    return None


def get_user_agent() -> Optional[str]:
    """Extract user agent from request."""
    if request:
        return request.headers.get("User-Agent", "")[:500]
    return None


def get_device_fingerprint() -> Optional[str]:
    """
    Generate a device fingerprint from request headers.
    This is a simple fingerprint based on user agent and other headers.
    For production, consider using more sophisticated methods.
    """
    if not request:
        return None
    
    components = []
    ua = request.headers.get("User-Agent", "")
    if ua:
        components.append(ua[:100])
    
    # Add more headers for fingerprinting
    accept_lang = request.headers.get("Accept-Language", "")
    if accept_lang:
        components.append(accept_lang[:50])
    
    # Simple hash-based fingerprint
    import hashlib
    fingerprint_data = "|".join(components)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:64]


def calculate_risk_score(
    user_id: int,
    ip_address: Optional[str],
    device_fingerprint: Optional[str],
    event_type: str = LoginEventType.LOGIN_SUCCESS.value
) -> tuple[float, List[str]]:
    """
    Calculate a risk score for a login event.
    
    Returns:
        tuple: (risk_score, list of risk factors)
    """
    risk_score = 0.0
    risk_factors = []
    
    # Factor 1: New IP address (0.3 weight)
    if ip_address:
        if is_new_ip(user_id, ip_address):
            risk_score += 0.3
            risk_factors.append("new_ip_address")
    
    # Factor 2: New device (0.25 weight)
    if device_fingerprint:
        if is_new_device(user_id, device_fingerprint):
            risk_score += 0.25
            risk_factors.append("new_device")
    
    # Factor 3: Unusual login time (0.15 weight)
    if is_unusual_time():
        risk_score += 0.15
        risk_factors.append("unusual_time")
    
    # Factor 4: Recent failed attempts (0.4 weight)
    recent_failures = get_recent_failed_attempts(user_id)
    if recent_failures >= 3:
        risk_score += min(0.4, recent_failures * 0.1)
        risk_factors.append(f"recent_failed_attempts:{recent_failures}")
    
    # Factor 5: Rapid successive attempts from different IPs (0.3 weight)
    if ip_address and has_rapid_location_change(user_id, ip_address):
        risk_score += 0.3
        risk_factors.append("rapid_location_change")
    
    # Cap at 1.0
    risk_score = min(1.0, risk_score)
    
    return risk_score, risk_factors


def is_new_ip(user_id: int, ip_address: str) -> bool:
    """Check if the IP address is new for this user."""
    # Check Redis cache first
    cache_key = USER_IPS_KEY.format(user_id=user_id)
    try:
        known_ips = redis_client.smembers(cache_key)
        if ip_address in known_ips:
            return False
    except Exception as e:
        logger.warning(f"Redis error checking known IPs: {e}")
    
    # Fall back to database
    existing = db.session.query(LoginEvent).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.ip_address == ip_address,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value
    ).first()
    
    return existing is None


def is_new_device(user_id: int, device_fingerprint: str) -> bool:
    """Check if the device is new for this user."""
    # Check Redis cache first
    cache_key = USER_DEVICES_KEY.format(user_id=user_id)
    try:
        known_devices = redis_client.smembers(cache_key)
        if device_fingerprint in known_devices:
            return False
    except Exception as e:
        logger.warning(f"Redis error checking known devices: {e}")
    
    # Fall back to database
    existing = db.session.query(LoginEvent).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.device_fingerprint == device_fingerprint,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value
    ).first()
    
    return existing is None


def is_unusual_time() -> bool:
    """
    Check if current time is unusual for login (e.g., late night).
    Unusual hours: 1 AM to 5 AM UTC
    """
    current_hour = datetime.utcnow().hour
    return 1 <= current_hour <= 5


def get_recent_failed_attempts(user_id: int, minutes: int = 15) -> int:
    """Get count of recent failed login attempts for a user."""
    since = datetime.utcnow() - timedelta(minutes=minutes)
    count = db.session.query(func.count(LoginEvent.id)).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_FAILED.value,
        LoginEvent.created_at >= since
    ).scalar()
    return count or 0


def has_rapid_location_change(user_id: int, current_ip: str) -> bool:
    """
    Check if there's a rapid location change (login from different IPs in short time).
    This is a simplified check - for production, use GeoIP for actual distance calculation.
    """
    recent_login = db.session.query(LoginEvent).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value,
        LoginEvent.created_at >= datetime.utcnow() - timedelta(hours=1)
    ).order_by(desc(LoginEvent.created_at)).first()
    
    if recent_login and recent_login.ip_address:
        return recent_login.ip_address != current_ip
    return False


def record_login_event(
    user_id: Optional[int],
    event_type: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    device_fingerprint: Optional[str] = None,
    location_country: Optional[str] = None,
    location_city: Optional[str] = None,
    risk_score: float = 0.0,
    risk_factors: Optional[List[str]] = None
) -> LoginEvent:
    """
    Record a login event and return the created event object.
    """
    event = LoginEvent(
        user_id=user_id,
        event_type=event_type,
        ip_address=ip_address or get_client_ip(),
        user_agent=user_agent or get_user_agent(),
        device_fingerprint=device_fingerprint or get_device_fingerprint(),
        location_country=location_country,
        location_city=location_city,
        risk_score=Decimal(str(risk_score)),
        risk_factors=json.dumps(risk_factors) if risk_factors else None
    )
    db.session.add(event)
    db.session.commit()
    
    # Update Redis cache for known IPs and devices
    if user_id and event_type == LoginEventType.LOGIN_SUCCESS.value:
        try:
            if event.ip_address:
                redis_key = USER_IPS_KEY.format(user_id=user_id)
                redis_client.sadd(redis_key, event.ip_address)
                redis_client.expire(redis_key, 86400 * 30)  # 30 days
            
            if event.device_fingerprint:
                redis_key = USER_DEVICES_KEY.format(user_id=user_id)
                redis_client.sadd(redis_key, event.device_fingerprint)
                redis_client.expire(redis_key, 86400 * 30)  # 30 days
        except Exception as e:
            logger.warning(f"Redis error updating known IPs/devices: {e}")
    
    logger.info(
        f"Recorded login event: user_id={user_id}, type={event_type}, "
        f"ip={event.ip_address}, risk_score={risk_score}"
    )
    
    return event


def check_brute_force(ip_address: str) -> bool:
    """
    Check if an IP is blocked due to brute force attempts.
    Returns True if the IP should be blocked.
    """
    if not ip_address:
        return False
    
    redis_key = BRUTE_FORCE_KEY.format(ip=ip_address)
    try:
        blocked = redis_client.get(redis_key + ":blocked")
        if blocked:
            return True
        
        attempts = redis_client.get(redis_key)
        if attempts and int(attempts) >= BRUTE_FORCE_THRESHOLD:
            # Block the IP
            redis_client.setex(
                redis_key + ":blocked",
                BRUTE_FORCE_BLOCK_MINUTES * 60,
                "1"
            )
            return True
    except Exception as e:
        logger.warning(f"Redis error checking brute force: {e}")
    
    return False


def record_failed_attempt(ip_address: str) -> int:
    """
    Record a failed login attempt for brute force detection.
    Returns the current count of failed attempts for this IP.
    """
    if not ip_address:
        return 0
    
    redis_key = BRUTE_FORCE_KEY.format(ip=ip_address)
    try:
        count = redis_client.incr(redis_key)
        redis_client.expire(redis_key, BRUTE_FORCE_WINDOW_MINUTES * 60)
        return count
    except Exception as e:
        logger.warning(f"Redis error recording failed attempt: {e}")
        return 0


def clear_brute_force_block(ip_address: str) -> None:
    """Clear brute force block for an IP (e.g., after successful login)."""
    if not ip_address:
        return
    
    redis_key = BRUTE_FORCE_KEY.format(ip=ip_address)
    try:
        redis_client.delete(redis_key)
        redis_client.delete(redis_key + ":blocked")
    except Exception as e:
        logger.warning(f"Redis error clearing brute force block: {e}")


def create_security_alert(
    user_id: int,
    alert_type: str,
    title: str,
    description: Optional[str] = None,
    severity: str = AlertSeverity.MEDIUM.value,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    login_event_id: Optional[int] = None
) -> SecurityAlert:
    """
    Create a security alert for a user.
    """
    alert = SecurityAlert(
        user_id=user_id,
        alert_type=alert_type,
        title=title,
        description=description,
        severity=severity,
        ip_address=ip_address,
        user_agent=user_agent,
        login_event_id=login_event_id
    )
    db.session.add(alert)
    db.session.commit()
    
    logger.warning(
        f"Created security alert: user_id={user_id}, type={alert_type}, "
        f"severity={severity}, title={title}"
    )
    
    return alert


def get_user_login_history(
    user_id: int,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Get login history for a user.
    """
    query = db.session.query(LoginEvent).filter(
        LoginEvent.user_id == user_id
    )
    
    if event_type:
        query = query.filter(LoginEvent.event_type == event_type)
    
    events = query.order_by(desc(LoginEvent.created_at)).offset(offset).limit(limit).all()
    return [e.to_dict() for e in events]


def get_user_alerts(
    user_id: int,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Get security alerts for a user.
    """
    query = db.session.query(SecurityAlert).filter(
        SecurityAlert.user_id == user_id
    )
    
    if status:
        query = query.filter(SecurityAlert.status == status)
    
    if severity:
        query = query.filter(SecurityAlert.severity == severity)
    
    alerts = query.order_by(desc(SecurityAlert.created_at)).offset(offset).limit(limit).all()
    return [a.to_dict() for a in alerts]


def acknowledge_alert(alert_id: int, user_id: int) -> Optional[SecurityAlert]:
    """
    Acknowledge a security alert.
    """
    alert = db.session.query(SecurityAlert).filter(
        SecurityAlert.id == alert_id,
        SecurityAlert.user_id == user_id
    ).first()
    
    if not alert:
        return None
    
    alert.status = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = user_id
    db.session.commit()
    
    logger.info(f"Acknowledged alert: id={alert_id}, user_id={user_id}")
    return alert


def acknowledge_all_alerts(user_id: int) -> int:
    """
    Acknowledge all active alerts for a user.
    Returns the count of acknowledged alerts.
    """
    result = db.session.query(SecurityAlert).filter(
        SecurityAlert.user_id == user_id,
        SecurityAlert.status == AlertStatus.ACTIVE.value
    ).update({
        "status": AlertStatus.ACKNOWLEDGED.value,
        "acknowledged_at": datetime.utcnow(),
        "acknowledged_by": user_id
    })
    db.session.commit()
    
    logger.info(f"Acknowledged all alerts: user_id={user_id}, count={result}")
    return result


def get_security_stats(user_id: int, days: int = 30) -> Dict[str, Any]:
    """
    Get security statistics for a user.
    """
    since = datetime.utcnow() - timedelta(days=days)
    
    # Login counts
    total_logins = db.session.query(func.count(LoginEvent.id)).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value,
        LoginEvent.created_at >= since
    ).scalar() or 0
    
    failed_logins = db.session.query(func.count(LoginEvent.id)).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_FAILED.value,
        LoginEvent.created_at >= since
    ).scalar() or 0
    
    # Unique IPs
    unique_ips = db.session.query(func.count(func.distinct(LoginEvent.ip_address))).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value,
        LoginEvent.created_at >= since
    ).scalar() or 0
    
    # Unique devices
    unique_devices = db.session.query(func.count(func.distinct(LoginEvent.device_fingerprint))).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value,
        LoginEvent.created_at >= since
    ).scalar() or 0
    
    # Alert counts
    active_alerts = db.session.query(func.count(SecurityAlert.id)).filter(
        SecurityAlert.user_id == user_id,
        SecurityAlert.status == AlertStatus.ACTIVE.value
    ).scalar() or 0
    
    total_alerts = db.session.query(func.count(SecurityAlert.id)).filter(
        SecurityAlert.user_id == user_id,
        SecurityAlert.created_at >= since
    ).scalar() or 0
    
    # Risk distribution
    high_risk_logins = db.session.query(func.count(LoginEvent.id)).filter(
        LoginEvent.user_id == user_id,
        LoginEvent.event_type == LoginEventType.LOGIN_SUCCESS.value,
        LoginEvent.risk_score >= RISK_THRESHOLD_HIGH,
        LoginEvent.created_at >= since
    ).scalar() or 0
    
    return {
        "period_days": days,
        "total_logins": total_logins,
        "failed_logins": failed_logins,
        "unique_ips": unique_ips,
        "unique_devices": unique_devices,
        "active_alerts": active_alerts,
        "total_alerts": total_alerts,
        "high_risk_logins": high_risk_logins,
        "login_success_rate": round(total_logins / max(1, total_logins + failed_logins) * 100, 1)
    }


def process_login(
    user: User,
    is_successful: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> tuple[Optional[LoginEvent], Optional[SecurityAlert], bool]:
    """
    Process a login attempt - detect anomalies and generate alerts.
    
    Args:
        user: The user attempting to login
        is_successful: Whether the login was successful
        ip_address: Client IP address
        user_agent: Client user agent
    
    Returns:
        tuple: (login_event, security_alert, should_block)
    """
    ip = ip_address or get_client_ip()
    ua = user_agent or get_user_agent()
    device_fp = get_device_fingerprint()
    
    # Check brute force
    if check_brute_force(ip):
        logger.warning(f"Brute force block triggered for IP: {ip}")
        event = record_login_event(
            user_id=user.id if user else None,
            event_type=LoginEventType.BRUTE_FORCE_BLOCKED.value,
            ip_address=ip,
            user_agent=ua
        )
        return event, None, True
    
    if not is_successful:
        # Record failed attempt
        count = record_failed_attempt(ip)
        
        event = record_login_event(
            user_id=user.id if user else None,
            event_type=LoginEventType.LOGIN_FAILED.value,
            ip_address=ip,
            user_agent=ua,
            device_fingerprint=device_fp
        )
        
        # Create alert if threshold reached
        alert = None
        if count >= BRUTE_FORCE_THRESHOLD:
            alert = create_security_alert(
                user_id=user.id,
                alert_type="brute_force_detected",
                title="Multiple Failed Login Attempts Detected",
                description=f"{count} failed login attempts from IP {ip}",
                severity=AlertSeverity.HIGH.value,
                ip_address=ip,
                user_agent=ua,
                login_event_id=event.id
            )
        
        return event, alert, False
    
    # Successful login
    # Calculate risk score
    risk_score, risk_factors = calculate_risk_score(
        user_id=user.id,
        ip_address=ip,
        device_fingerprint=device_fp,
        event_type=LoginEventType.LOGIN_SUCCESS.value
    )
    
    # Clear brute force counter on successful login
    clear_brute_force_block(ip)
    
    # Record login event
    event = record_login_event(
        user_id=user.id,
        event_type=LoginEventType.LOGIN_SUCCESS.value,
        ip_address=ip,
        user_agent=ua,
        device_fingerprint=device_fp,
        risk_score=risk_score,
        risk_factors=risk_factors
    )
    
    # Create alert if risk is high enough
    alert = None
    if risk_score >= RISK_THRESHOLD_MEDIUM:
        severity = AlertSeverity.HIGH.value if risk_score >= RISK_THRESHOLD_HIGH else AlertSeverity.MEDIUM.value
        
        alert = create_security_alert(
            user_id=user.id,
            alert_type="suspicious_login",
            title="Suspicious Login Detected",
            description=f"Risk factors: {', '.join(risk_factors)}. Risk score: {risk_score:.2f}",
            severity=severity,
            ip_address=ip,
            user_agent=ua,
            login_event_id=event.id
        )
    
    # Log to audit (with backward compatibility for existing databases)
    try:
        audit = AuditLog(
            user_id=user.id,
            action=f"login_success (risk: {risk_score:.2f})",
            ip_address=ip,
            details=json.dumps({"risk_factors": risk_factors}) if risk_factors else None
        )
        db.session.add(audit)
        db.session.commit()
    except TypeError:
        # Fallback for databases without new columns
        audit = AuditLog(
            user_id=user.id,
            action=f"login_success (risk: {risk_score:.2f})"
        )
        db.session.add(audit)
        db.session.commit()
    
    return event, alert, False


# ============================================================================
# Device Trust Management
# ============================================================================

from ..models import TrustedDevice


def get_trusted_devices(user_id: int) -> List[Dict[str, Any]]:
    """
    Get all trusted devices for a user.
    """
    devices = db.session.query(TrustedDevice).filter(
        TrustedDevice.user_id == user_id,
        TrustedDevice.is_active == True
    ).order_by(desc(TrustedDevice.last_used_at)).all()
    
    return [d.to_dict() for d in devices]


def trust_device(
    user_id: int,
    device_fingerprint: str,
    device_name: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> TrustedDevice:
    """
    Mark a device as trusted for a user.
    """
    # Check if already trusted
    existing = db.session.query(TrustedDevice).filter(
        TrustedDevice.user_id == user_id,
        TrustedDevice.device_fingerprint == device_fingerprint
    ).first()
    
    if existing:
        # Update existing
        existing.is_active = True
        existing.last_used_at = datetime.utcnow()
        existing.device_name = device_name or existing.device_name
        existing.ip_address = ip_address or existing.ip_address
        db.session.commit()
        logger.info(f"Updated trusted device: user_id={user_id}, device={device_fingerprint[:16]}")
        return existing
    
    # Create new trusted device
    device = TrustedDevice(
        user_id=user_id,
        device_fingerprint=device_fingerprint,
        device_name=device_name,
        user_agent=user_agent,
        ip_address=ip_address
    )
    db.session.add(device)
    db.session.commit()
    
    logger.info(f"Created trusted device: user_id={user_id}, device={device_fingerprint[:16]}")
    return device


def remove_device_trust(user_id: int, device_id: int) -> bool:
    """
    Remove trust from a device.
    """
    device = db.session.query(TrustedDevice).filter(
        TrustedDevice.id == device_id,
        TrustedDevice.user_id == user_id
    ).first()
    
    if not device:
        return False
    
    device.is_active = False
    db.session.commit()
    
    logger.info(f"Removed device trust: user_id={user_id}, device_id={device_id}")
    return True


def remove_trust_by_fingerprint(user_id: int, device_fingerprint: str) -> bool:
    """
    Remove trust from a device by fingerprint.
    """
    device = db.session.query(TrustedDevice).filter(
        TrustedDevice.user_id == user_id,
        TrustedDevice.device_fingerprint == device_fingerprint
    ).first()
    
    if not device:
        return False
    
    device.is_active = False
    db.session.commit()
    
    logger.info(f"Removed device trust by fingerprint: user_id={user_id}")
    return True


def is_device_trusted(user_id: int, device_fingerprint: str) -> bool:
    """
    Check if a device is trusted for a user.
    """
    device = db.session.query(TrustedDevice).filter(
        TrustedDevice.user_id == user_id,
        TrustedDevice.device_fingerprint == device_fingerprint,
        TrustedDevice.is_active == True
    ).first()
    
    return device is not None


def update_device_last_used(user_id: int, device_fingerprint: str) -> None:
    """
    Update the last used timestamp for a trusted device.
    """
    device = db.session.query(TrustedDevice).filter(
        TrustedDevice.user_id == user_id,
        TrustedDevice.device_fingerprint == device_fingerprint,
        TrustedDevice.is_active == True
    ).first()
    
    if device:
        device.last_used_at = datetime.utcnow()
        device.ip_address = get_client_ip()
        db.session.commit()


def get_device_by_id(user_id: int, device_id: int) -> Optional[TrustedDevice]:
    """
    Get a specific trusted device by ID.
    """
    return db.session.query(TrustedDevice).filter(
        TrustedDevice.id == device_id,
        TrustedDevice.user_id == user_id
    ).first()