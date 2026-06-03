from datetime import timezone
"""
Login anomaly detection and suspicious activity alerts.
"""
import hashlib
import os
from datetime import datetime, timedelta
from ..extensions import db


# Pepper for hashing PII (should be in environment variable)
PII_PEPPER = os.environ.get("PII_PEPPER", "default-pepper-change-in-production")


class LoginEvent(db.Model):
    __tablename__ = "login_events"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ip_address_hash = db.Column(db.String(64), nullable=False)  # SHA256 hash
    user_agent = db.Column(db.String(500), nullable=True)
    success = db.Column(db.Boolean, nullable=False)
    anomaly_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add index for faster queries
    __table_args__ = (
        db.Index('idx_user_created', 'user_id', 'created_at'),
    )


def hash_ip(ip: str) -> str:
    """Hash IP address with pepper for PII protection."""
    return hashlib.sha256(f"{ip}{PII_PEPPER}".encode()).hexdigest()


def detect_anomaly(user_id: int, ip: str, user_agent: str = "", success: bool = True) -> dict:
    """Detect login anomalies based on historical patterns.
    
    Args:
        user_id: User ID
        ip: IP address (will be hashed for storage)
        user_agent: User agent string
        success: Whether login was successful
        
    Returns:
        dict with anomaly detection results
    """
    # Hash IP for privacy
    ip_hash = hash_ip(ip)
    
    # Record this login event
    event = LoginEvent(
        user_id=user_id,
        ip_address_hash=ip_hash,
        user_agent=user_agent,
        success=success,
    )
    db.session.add(event)
    db.session.commit()
    
    # Get recent events for analysis
    recent = LoginEvent.query.filter(
        LoginEvent.user_id == user_id,
        LoginEvent.created_at > datetime.now(timezone.utc) - timedelta(days=30)
    ).all()
    
    if len(recent) <= 1:
        return {"anomaly": False, "score": 0, "reason": "first_login"}
    
    # Check for new IP
    known_ips = set(e.ip_address_hash for e in recent[:-1])  # Exclude current
    new_ip = ip_hash not in known_ips
    
    # Check for rapid attempts
    last_hour = [e for e in recent if e.created_at > datetime.now(timezone.utc) - timedelta(hours=1)]
    rapid_attempts = len(last_hour) > 5
    
    # Check for failed logins
    recent_failures = [e for e in recent[:-1] if not e.success and 
                       e.created_at > datetime.now(timezone.utc) - timedelta(hours=24)]
    has_failures = len(recent_failures) > 3
    
    # Calculate score with configurable threshold
    threshold = float(os.environ.get("ANOMALY_THRESHOLD", "0.5"))
    
    score = 0.0
    reasons = []
    
    if new_ip:
        score += 0.3
        reasons.append("new_ip")
    if rapid_attempts:
        score += 0.5
        reasons.append("rapid_attempts")
    if has_failures:
        score += 0.4
        reasons.append("recent_failures")
    
    # Update anomaly score on the event
    event.anomaly_score = score
    db.session.commit()
    
    return {
        "anomaly": score > threshold,
        "score": score,
        "reasons": reasons,
        "new_ip": new_ip,
        "recent_attempts": len(last_hour),
        "recent_failures": len(recent_failures),
    }
