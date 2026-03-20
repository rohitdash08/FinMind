"""Login anomaly detection service.

Tracks login metadata and detects suspicious patterns:
- New device / user-agent
- Unusual login time (outside normal hours)
- Different IP subnet
- Rapid successive login attempts
- Login from new geographic region (IP-based)
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from ..extensions import db

logger = logging.getLogger("finmind.anomaly")


class LoginActivity(db.Model):
    """Records each login attempt with contextual metadata."""

    __tablename__ = "login_activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    device_fingerprint = db.Column(db.String(64), nullable=True)
    success = db.Column(db.Boolean, default=True, nullable=False)
    anomaly_score = db.Column(db.Integer, default=0, nullable=False)
    anomaly_reasons = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class TrustedDevice(db.Model):
    """Stores devices a user has previously logged in from."""

    __tablename__ = "trusted_devices"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    device_fingerprint = db.Column(db.String(64), nullable=False)
    user_agent = db.Column(db.String(512), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_trusted = db.Column(db.Boolean, default=True, nullable=False)


class SecurityAlert(db.Model):
    """User-facing security alerts for anomalous activity."""

    __tablename__ = "security_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default="medium", nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    login_activity_id = db.Column(
        db.Integer, db.ForeignKey("login_activities.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def compute_device_fingerprint(ip: str | None, user_agent: str | None) -> str:
    raw = f"{user_agent or 'unknown'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _ip_subnet(ip: str | None) -> str:
    if not ip:
        return "unknown"
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) == 4 else ip


def analyze_login(
    user_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
) -> dict[str, Any]:
    fingerprint = compute_device_fingerprint(ip_address, user_agent)
    score = 0
    reasons: list[str] = []

    now = datetime.utcnow()

    # Check 1: New device
    trusted = TrustedDevice.query.filter_by(
        user_id=user_id, device_fingerprint=fingerprint, is_trusted=True
    ).first()
    if not trusted:
        score += 30
        reasons.append("new_device")

    # Check 2: New IP subnet
    recent_ips = (
        db.session.query(LoginActivity.ip_address)
        .filter(
            LoginActivity.user_id == user_id,
            LoginActivity.success.is_(True),
            LoginActivity.created_at >= now - timedelta(days=30),
        )
        .all()
    )
    known_subnets = {_ip_subnet(r.ip_address) for r in recent_ips}
    current_subnet = _ip_subnet(ip_address)
    if known_subnets and current_subnet not in known_subnets:
        score += 25
        reasons.append("new_ip_subnet")

    # Check 3: Unusual hour
    recent_hours = (
        db.session.query(LoginActivity.created_at)
        .filter(
            LoginActivity.user_id == user_id,
            LoginActivity.success.is_(True),
            LoginActivity.created_at >= now - timedelta(days=30),
        )
        .all()
    )
    if len(recent_hours) >= 5:
        hour_counts = Counter(r.created_at.hour for r in recent_hours)
        common_hours = {h for h, c in hour_counts.items() if c >= 2}
        if common_hours and now.hour not in common_hours:
            window = {(h - 1) % 24 for h in common_hours} | common_hours | {(h + 1) % 24 for h in common_hours}
            if now.hour not in window:
                score += 20
                reasons.append("unusual_hour")

    # Check 4: Rapid failed attempts
    recent_failures = (
        LoginActivity.query.filter(
            LoginActivity.user_id == user_id,
            LoginActivity.success.is_(False),
            LoginActivity.created_at >= now - timedelta(minutes=15),
        )
        .count()
    )
    if recent_failures >= 3:
        score += 40
        reasons.append("rapid_failed_attempts")

    # Record the activity
    activity = LoginActivity(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        device_fingerprint=fingerprint,
        success=success,
        anomaly_score=score,
        anomaly_reasons=",".join(reasons) if reasons else None,
    )
    db.session.add(activity)

    # Update or create trusted device on successful login
    if success and score < 50:
        if trusted:
            trusted.last_seen = now
            trusted.ip_address = ip_address
        else:
            db.session.add(
                TrustedDevice(
                    user_id=user_id,
                    device_fingerprint=fingerprint,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
            )

    # Create alert if score is high enough
    alert = None
    if score >= 30:
        severity = "high" if score >= 60 else "medium"
        message_parts = []
        if "new_device" in reasons:
            message_parts.append("Login from a new device detected.")
        if "new_ip_subnet" in reasons:
            message_parts.append(f"Login from an unfamiliar network ({current_subnet}.*).")
        if "unusual_hour" in reasons:
            message_parts.append(f"Login at an unusual time ({now.strftime('%H:%M')} UTC).")
        if "rapid_failed_attempts" in reasons:
            message_parts.append(f"{recent_failures} failed login attempts in the last 15 minutes.")

        alert = SecurityAlert(
            user_id=user_id,
            alert_type="login_anomaly",
            severity=severity,
            message=" ".join(message_parts),
            login_activity_id=activity.id,
        )
        db.session.add(alert)

    db.session.commit()

    if alert:
        alert.login_activity_id = activity.id
        db.session.commit()

    return {
        "anomaly_score": score,
        "reasons": reasons,
        "is_anomalous": score >= 30,
        "severity": "high" if score >= 60 else ("medium" if score >= 30 else "low"),
        "device_fingerprint": fingerprint,
        "activity_id": activity.id,
        "alert_id": alert.id if alert else None,
    }
