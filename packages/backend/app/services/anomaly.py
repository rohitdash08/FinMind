
"""
Login anomaly detection and suspicious activity alerts.
"""
from datetime import datetime, timedelta
from ..extensions import db


class LoginEvent(db.Model):
    __tablename__ = "login_events"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(500), nullable=True)
    success = db.Column(db.Boolean, nullable=False)
    anomaly_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def detect_anomaly(user_id: int, ip: str, user_agent: str = None) -> dict:
    """Detect login anomalies based on historical patterns."""
    recent = LoginEvent.query.filter(
        LoginEvent.user_id == user_id,
        LoginEvent.created_at > datetime.utcnow() - timedelta(days=30)
    ).all()
    
    if not recent:
        return {"anomaly": False, "score": 0, "reason": "first_login"}
    
    # Check for new IP
    known_ips = set(e.ip_address for e in recent)
    new_ip = ip not in known_ips
    
    # Check for rapid attempts
    last_hour = [e for e in recent if e.created_at > datetime.utcnow() - timedelta(hours=1)]
    rapid_attempts = len(last_hour) > 5
    
    # Calculate score
    score = 0
    reasons = []
    if new_ip:
        score += 0.3
        reasons.append("new_ip")
    if rapid_attempts:
        score += 0.5
        reasons.append("rapid_attempts")
    
    return {
        "anomaly": score > 0.5,
        "score": score,
        "reasons": reasons,
        "new_ip": new_ip,
        "recent_attempts": len(last_hour)
    }
