
"""
Device trust management and recognition.
Tracks trusted devices and flags new/suspicious logins.
"""
from datetime import datetime
from ..extensions import db


class TrustedDevice(db.Model):
    __tablename__ = "trusted_devices"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    device_fingerprint = db.Column(db.String(255), nullable=False)
    device_name = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    trusted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def is_trusted_device(user_id: int, fingerprint: str) -> bool:
    """Check if device is trusted."""
    device = TrustedDevice.query.filter_by(
        user_id=user_id, device_fingerprint=fingerprint, trusted=True
    ).first()
    return device is not None


def register_device(user_id: int, fingerprint: str, name: str = None, ip: str = None) -> TrustedDevice:
    """Register a new device."""
    device = TrustedDevice(
        user_id=user_id,
        device_fingerprint=fingerprint,
        device_name=name,
        ip_address=ip,
    )
    db.session.add(device)
    db.session.commit()
    return device


def trust_device(user_id: int, fingerprint: str) -> bool:
    """Mark a device as trusted."""
    device = TrustedDevice.query.filter_by(
        user_id=user_id, device_fingerprint=fingerprint
    ).first()
    if device:
        device.trusted = True
        db.session.commit()
        return True
    return False
