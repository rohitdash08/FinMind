"""
Login event tracking and anomaly detection models.
"""
from datetime import datetime
from .extensions import db


class LoginEvent(db.Model):
    """Records each login attempt for anomaly detection."""
    __tablename__ = "login_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    success = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="login_events")


class LoginAlert(db.Model):
    """Stores anomaly alerts for suspicious login activity."""
    __tablename__ = "login_alerts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    severity = db.Column(db.String(20), default="medium", nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    login_event_id = db.Column(db.Integer, db.ForeignKey("login_events.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="login_alerts")
    login_event = db.relationship("LoginEvent", backref="alerts")
