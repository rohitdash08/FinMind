"""
Device Trust Management & Recognition (issue #125)

Allow users to view and manage trusted devices.
Trusted devices skip additional auth challenges.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional
from app.extensions import db


class TrustedDevice(db.Model):
    """A device trusted by a user for authentication."""

    __tablename__ = "trusted_devices"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    device_token = db.Column(db.String(64), unique=True, nullable=False)
    device_name = db.Column(db.String(200), nullable=False)
    device_fingerprint = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    is_trusted = db.Column(db.Boolean, default=True, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    trusted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_name": self.device_name,
            "device_token": self.device_token,
            "device_fingerprint": self.device_fingerprint,
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "is_trusted": self.is_trusted,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "trusted_at": self.trusted_at.isoformat() if self.trusted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_expired": self._is_expired(),
        }

    def _is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


def _generate_device_token() -> str:
    """Generate a cryptographically secure device token."""
    return secrets.token_hex(32)  # 64-char hex string


def _fingerprint_device(user_agent: str, ip_address: str) -> str:
    """Create a deterministic fingerprint from device characteristics."""
    raw = f"{user_agent}|{ip_address}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def register_device(
    user_id: int,
    device_name: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    trust_days: Optional[int] = 30,
) -> TrustedDevice:
    """Register a new trusted device for a user."""
    device_token = _generate_device_token()
    fingerprint = None
    if user_agent and ip_address:
        fingerprint = _fingerprint_device(user_agent, ip_address)

    expires_at = None
    if trust_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=trust_days)

    device = TrustedDevice(
        user_id=user_id,
        device_token=device_token,
        device_name=device_name,
        device_fingerprint=fingerprint,
        user_agent=user_agent,
        ip_address=ip_address,
        is_trusted=True,
        expires_at=expires_at,
    )
    db.session.add(device)
    db.session.commit()
    return device


def verify_device_token(token: str, user_id: Optional[int] = None) -> Optional[TrustedDevice]:
    """
    Verify a device token.
    Returns the TrustedDevice if valid, trusted, and not expired. None otherwise.
    """
    query = TrustedDevice.query.filter_by(device_token=token, is_trusted=True)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    device = query.first()

    if not device:
        return None

    if device._is_expired():
        return None

    # Update last seen
    device.last_seen_at = datetime.utcnow()
    db.session.commit()
    return device


def revoke_device(device_id: int, user_id: int) -> Optional[TrustedDevice]:
    """
    Revoke trust for a specific device.
    Returns the device if revoked, None if not found or not owned by user.
    """
    device = TrustedDevice.query.filter_by(id=device_id, user_id=user_id).first()
    if not device:
        return None
    device.is_trusted = False
    db.session.commit()
    return device


def revoke_all_devices(user_id: int, except_token: Optional[str] = None) -> int:
    """
    Revoke all trusted devices for a user.
    If except_token is given, that device is kept.
    Returns count of revoked devices.
    """
    query = TrustedDevice.query.filter_by(user_id=user_id, is_trusted=True)
    if except_token:
        query = query.filter(TrustedDevice.device_token != except_token)
    devices = query.all()
    for d in devices:
        d.is_trusted = False
    db.session.commit()
    return len(devices)


def get_user_devices(user_id: int, include_revoked: bool = False) -> list[dict]:
    """Get all devices for a user."""
    query = TrustedDevice.query.filter_by(user_id=user_id)
    if not include_revoked:
        query = query.filter_by(is_trusted=True)
    devices = query.order_by(TrustedDevice.last_seen_at.desc()).all()
    return [d.to_dict() for d in devices]


def recognize_device(
    user_id: int,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[TrustedDevice]:
    """
    Auto-recognize a device by fingerprint without requiring a token.
    Returns a trusted, non-expired device if fingerprint matches.
    """
    if not user_agent or not ip_address:
        return None

    fingerprint = _fingerprint_device(user_agent, ip_address)
    device = TrustedDevice.query.filter_by(
        user_id=user_id,
        device_fingerprint=fingerprint,
        is_trusted=True,
    ).first()

    if device and device._is_expired():
        return None

    if device:
        device.last_seen_at = datetime.utcnow()
        db.session.commit()

    return device