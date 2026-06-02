"""
Device trust management and recognition.
Tracks trusted devices and flags new/suspicious logins.
"""
import hashlib
import os
from datetime import datetime
from ..extensions import db


# Pepper for hashing PII (should be in environment variable)
PII_PEPPER = os.environ.get("PII_PEPPER", "default-pepper-change-in-production")


class TrustedDevice(db.Model):
    __tablename__ = "trusted_devices"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    device_fingerprint_hash = db.Column(db.String(64), nullable=False)  # SHA256 hash
    device_name = db.Column(db.String(100), nullable=True)
    ip_address_hash = db.Column(db.String(64), nullable=True)  # SHA256 hash
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    trusted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add unique constraint to prevent duplicates
    __table_args__ = (
        db.UniqueConstraint('user_id', 'device_fingerprint_hash', name='uq_user_device'),
        db.Index('idx_user_fingerprint', 'user_id', 'device_fingerprint_hash'),
    )


def hash_fingerprint(fingerprint: str) -> str:
    """Hash device fingerprint with pepper for PII protection."""
    return hashlib.sha256(f"{fingerprint}{PII_PEPPER}".encode()).hexdigest()


def hash_ip(ip: str) -> str:
    """Hash IP address with pepper for PII protection."""
    return hashlib.sha256(f"{ip}{PII_PEPPER}".encode()).hexdigest()


def is_trusted_device(user_id: int, fingerprint: str) -> bool:
    """Check if device is trusted and update last_seen."""
    fingerprint_hash = hash_fingerprint(fingerprint)
    
    device = TrustedDevice.query.filter_by(
        user_id=user_id, 
        device_fingerprint_hash=fingerprint_hash, 
        trusted=True
    ).first()
    
    if device:
        # Update last_seen
        device.last_seen = datetime.utcnow()
        db.session.commit()
        return True
    
    return False


def register_device(user_id: int, fingerprint: str, name: str = None, ip: str = None) -> TrustedDevice:
    """Register a new device or update existing one (upsert)."""
    fingerprint_hash = hash_fingerprint(fingerprint)
    ip_hash = hash_ip(ip) if ip else None
    
    # Check if device already exists
    existing = TrustedDevice.query.filter_by(
        user_id=user_id,
        device_fingerprint_hash=fingerprint_hash
    ).first()
    
    if existing:
        # Update existing device
        existing.last_seen = datetime.utcnow()
        if ip_hash:
            existing.ip_address_hash = ip_hash
        if name:
            existing.device_name = name
        db.session.commit()
        return existing
    
    # Create new device
    device = TrustedDevice(
        user_id=user_id,
        device_fingerprint_hash=fingerprint_hash,
        device_name=name,
        ip_address_hash=ip_hash,
    )
    db.session.add(device)
    db.session.commit()
    return device


def trust_device(user_id: int, fingerprint: str) -> bool:
    """Mark a device as trusted."""
    fingerprint_hash = hash_fingerprint(fingerprint)
    
    device = TrustedDevice.query.filter_by(
        user_id=user_id, 
        device_fingerprint_hash=fingerprint_hash
    ).first()
    
    if device:
        device.trusted = True
        device.last_seen = datetime.utcnow()
        db.session.commit()
        return True
    
    return False
