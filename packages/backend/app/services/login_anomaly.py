"""Login anomaly detection and suspicious activity alerts.

Provides:
- Login event tracking with device/location metadata
- Anomaly detection via configurable risk scoring
- Automated security alert generation
- Login history analysis and reporting
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models import LoginEvent, SecurityAlert


# ─── User-Agent Parsing ─────────────────────────────────────────────


def _parse_user_agent(ua: str) -> dict:
    """Extract device info from User-Agent string."""
    ua_lower = ua.lower() if ua else ""

    # Device type
    if any(k in ua_lower for k in ("mobile", "android", "iphone")):
        device_type = "mobile"
    elif "ipad" in ua_lower or "tablet" in ua_lower:
        device_type = "tablet"
    else:
        device_type = "desktop"

    # Browser
    browser = "Unknown"
    if "firefox" in ua_lower:
        browser = "Firefox"
    elif "edg" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower:
        browser = "Chrome"
    elif "safari" in ua_lower:
        browser = "Safari"

    # OS
    os_name = "Unknown"
    if "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "windows" in ua_lower:
        os_name = "Windows"
    elif "mac os" in ua_lower:
        os_name = "macOS"
    elif "linux" in ua_lower:
        os_name = "Linux"

    return {"device_type": device_type, "browser": browser, "os": os_name}


# ─── Anomaly Detection ──────────────────────────────────────────────

# Risk weights for different anomaly signals
RISK_WEIGHTS = {
    "new_ip": 0.3,
    "new_device": 0.25,
    "unusual_time": 0.15,
    "rapid_attempts": 0.4,
    "new_country": 0.35,
    "failed_streak": 0.5,
    "concurrent_sessions": 0.2,
}


def _analyze_login(user_id: int, ip_address: str, user_agent: str,
                   event_type: str = "login") -> dict:
    """Analyze a login attempt for anomalies.

    Returns:
        Dict with risk_score, is_suspicious, and anomaly_reasons
    """
    reasons = []
    risk_score = 0.0
    ua_info = _parse_user_agent(user_agent)

    # Look at recent login history
    recent_events = (LoginEvent.query
                     .filter_by(user_id=user_id)
                     .order_by(LoginEvent.created_at.desc())
                     .limit(100)
                     .all())

    if recent_events:
        # Check 1: New IP address
        known_ips = {e.ip_address for e in recent_events if e.ip_address}
        if ip_address and ip_address not in known_ips:
            reasons.append("new_ip")
            risk_score += RISK_WEIGHTS["new_ip"]

        # Check 2: New device/browser
        known_agents = {(e.browser, e.os) for e in recent_events}
        if (ua_info["browser"], ua_info["os"]) not in known_agents:
            reasons.append("new_device")
            risk_score += RISK_WEIGHTS["new_device"]

        # Check 3: Unusual time (login outside normal hours)
        now = datetime.utcnow()
        recent_hours = [e.created_at.hour for e in recent_events
                        if e.created_at and e.event_type == "login"]
        if recent_hours:
            avg_hour = sum(recent_hours) / len(recent_hours)
            hour_diff = abs(now.hour - avg_hour)
            if hour_diff > 8:
                reasons.append("unusual_time")
                risk_score += RISK_WEIGHTS["unusual_time"]

        # Check 4: Rapid login attempts (>5 in last 10 minutes)
        ten_min_ago = now - timedelta(minutes=10)
        rapid_count = sum(1 for e in recent_events
                          if e.created_at and e.created_at > ten_min_ago)
        if rapid_count >= 5:
            reasons.append("rapid_attempts")
            risk_score += RISK_WEIGHTS["rapid_attempts"]

        # Check 5: Recent failed login streak
        failed_streak = 0
        for e in recent_events:
            if e.event_type == "failed_login":
                failed_streak += 1
            else:
                break
        if failed_streak >= 3:
            reasons.append("failed_streak")
            risk_score += RISK_WEIGHTS["failed_streak"]

    # Cap risk score at 1.0
    risk_score = min(risk_score, 1.0)
    is_suspicious = risk_score >= 0.5

    return {
        "risk_score": round(risk_score, 3),
        "is_suspicious": is_suspicious,
        "anomaly_reasons": reasons,
        "device_info": ua_info,
    }


# ─── Event Recording ────────────────────────────────────────────────


def record_login_event(user_id: int, ip_address: str = "",
                       user_agent: str = "",
                       event_type: str = "login",
                       session_id: str = "") -> dict:
    """Record a login event and check for anomalies.

    Args:
        user_id: User ID
        ip_address: Client IP
        user_agent: HTTP User-Agent
        event_type: login, failed_login, logout
        session_id: Optional session identifier

    Returns:
        Dict with event info and anomaly analysis
    """
    analysis = _analyze_login(user_id, ip_address, user_agent, event_type)
    ua_info = analysis["device_info"]

    event = LoginEvent(
        user_id=user_id,
        event_type=event_type,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        device_type=ua_info["device_type"],
        browser=ua_info["browser"],
        os=ua_info["os"],
        is_suspicious=analysis["is_suspicious"],
        risk_score=analysis["risk_score"],
        anomaly_reasons=json.dumps(analysis["anomaly_reasons"]) if analysis["anomaly_reasons"] else None,
        session_id=session_id or None,
    )
    db.session.add(event)
    db.session.commit()

    # Generate alerts for suspicious activity
    if analysis["is_suspicious"]:
        _generate_alerts(user_id, analysis, ip_address, ua_info)

    return {
        "event_id": event.id,
        "event_type": event_type,
        "risk_score": analysis["risk_score"],
        "is_suspicious": analysis["is_suspicious"],
        "anomaly_reasons": analysis["anomaly_reasons"],
        "device_type": ua_info["device_type"],
        "browser": ua_info["browser"],
        "os": ua_info["os"],
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _generate_alerts(user_id: int, analysis: dict,
                     ip_address: str, ua_info: dict):
    """Create security alerts for suspicious activity."""
    reasons = analysis["anomaly_reasons"]

    if "new_ip" in reasons:
        _create_alert(
            user_id=user_id,
            alert_type="new_ip_login",
            severity="medium",
            title="Login from new IP address",
            description=f"A login was detected from IP {ip_address}, "
                        f"which has not been used before.",
            metadata={"ip_address": ip_address},
        )

    if "new_device" in reasons:
        _create_alert(
            user_id=user_id,
            alert_type="new_device",
            severity="medium",
            title="Login from new device",
            description=f"A login from {ua_info['browser']} on {ua_info['os']} "
                        f"was detected for the first time.",
            metadata={"browser": ua_info["browser"], "os": ua_info["os"]},
        )

    if "rapid_attempts" in reasons:
        _create_alert(
            user_id=user_id,
            alert_type="rapid_attempts",
            severity="high",
            title="Multiple rapid login attempts detected",
            description="Multiple login attempts in a short period were detected. "
                        "Your account may be under attack.",
            metadata={"ip_address": ip_address},
        )

    if "failed_streak" in reasons:
        _create_alert(
            user_id=user_id,
            alert_type="failed_streak",
            severity="high",
            title="Multiple failed login attempts",
            description="Several consecutive failed login attempts were recorded.",
            metadata={"ip_address": ip_address},
        )


def _create_alert(user_id: int, alert_type: str, severity: str,
                  title: str, description: str, metadata: dict | None = None):
    """Create a security alert."""
    alert = SecurityAlert(
        user_id=user_id,
        alert_type=alert_type,
        severity=severity,
        title=title,
        description=description,
        metadata_=json.dumps(metadata) if metadata else None,
    )
    db.session.add(alert)
    db.session.commit()


# ─── Query Functions ─────────────────────────────────────────────────


def get_login_history(user_id: int, limit: int = 50,
                      event_type: str | None = None,
                      suspicious_only: bool = False) -> list[dict]:
    """Get login event history.

    Args:
        user_id: User ID
        limit: Max records
        event_type: Filter by event type
        suspicious_only: Show only suspicious events

    Returns:
        List of login event dicts
    """
    query = LoginEvent.query.filter_by(user_id=user_id)

    if event_type:
        query = query.filter_by(event_type=event_type)
    if suspicious_only:
        query = query.filter_by(is_suspicious=True)

    events = query.order_by(LoginEvent.created_at.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "ip_address": e.ip_address,
            "device_type": e.device_type,
            "browser": e.browser,
            "os": e.os,
            "is_suspicious": e.is_suspicious,
            "risk_score": e.risk_score,
            "anomaly_reasons": json.loads(e.anomaly_reasons) if e.anomaly_reasons else [],
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


def get_security_alerts(user_id: int, limit: int = 50,
                        unacknowledged_only: bool = False) -> list[dict]:
    """Get security alerts for a user.

    Args:
        user_id: User ID
        limit: Max number of alerts
        unacknowledged_only: Show only unacknowledged alerts

    Returns:
        List of alert dicts
    """
    query = SecurityAlert.query.filter_by(user_id=user_id)

    if unacknowledged_only:
        query = query.filter_by(acknowledged=False)

    alerts = query.order_by(SecurityAlert.created_at.desc()).limit(limit).all()

    return [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "description": a.description,
            "metadata": json.loads(a.metadata_) if a.metadata_ else None,
            "acknowledged": a.acknowledged,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


def acknowledge_alert(user_id: int, alert_id: int) -> bool:
    """Acknowledge a security alert.

    Args:
        user_id: User ID
        alert_id: Alert ID

    Returns:
        True if acknowledged, False if not found
    """
    alert = SecurityAlert.query.filter_by(
        id=alert_id, user_id=user_id
    ).first()

    if not alert:
        return False

    alert.acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    db.session.commit()
    return True


def acknowledge_all_alerts(user_id: int) -> int:
    """Acknowledge all unacknowledged alerts.

    Returns:
        Number of alerts acknowledged
    """
    alerts = SecurityAlert.query.filter_by(
        user_id=user_id, acknowledged=False
    ).all()

    count = 0
    for a in alerts:
        a.acknowledged = True
        a.acknowledged_at = datetime.utcnow()
        count += 1

    db.session.commit()
    return count


def get_login_stats(user_id: int, days: int = 30) -> dict:
    """Get login statistics for a user.

    Args:
        user_id: User ID
        days: Number of days to look back

    Returns:
        Dict with login statistics
    """
    since = datetime.utcnow() - timedelta(days=days)
    events = LoginEvent.query.filter(
        LoginEvent.user_id == user_id,
        LoginEvent.created_at >= since,
    ).all()

    total = len(events)
    logins = sum(1 for e in events if e.event_type == "login")
    failed = sum(1 for e in events if e.event_type == "failed_login")
    suspicious = sum(1 for e in events if e.is_suspicious)

    unique_ips = len({e.ip_address for e in events if e.ip_address})
    unique_devices = len({(e.browser, e.os) for e in events})

    # Risk distribution
    risk_levels = {"low": 0, "medium": 0, "high": 0}
    for e in events:
        if e.risk_score < 0.3:
            risk_levels["low"] += 1
        elif e.risk_score < 0.6:
            risk_levels["medium"] += 1
        else:
            risk_levels["high"] += 1

    # Unacknowledged alerts
    unack_alerts = SecurityAlert.query.filter_by(
        user_id=user_id, acknowledged=False
    ).count()

    return {
        "period_days": days,
        "total_events": total,
        "successful_logins": logins,
        "failed_logins": failed,
        "suspicious_events": suspicious,
        "unique_ips": unique_ips,
        "unique_devices": unique_devices,
        "risk_distribution": risk_levels,
        "unacknowledged_alerts": unack_alerts,
    }
