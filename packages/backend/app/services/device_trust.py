"""
device_trust.py — Device recognition and trust management service.

Records every login attempt with device fingerprint (SHA-256 of user-agent + IP).
Tracks new vs. known devices, trusted/untrusted status.

Public API:
    record_login(uid, user_agent, ip_address, session) -> dict
    fingerprint(user_agent, ip_address) -> str
    device_to_dict(device) -> dict
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import TrustedDevice

logger = logging.getLogger("finmind.device_trust")


def fingerprint(user_agent: str | None, ip_address: str | None) -> str:
    """Generate a stable SHA-256 fingerprint from user-agent + IP."""
    raw = f"{(user_agent or '').strip()}|{(ip_address or '').strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def record_login(
    uid: int,
    user_agent: str | None,
    ip_address: str | None,
    session: Session,
) -> dict:
    """
    Record a login event. Creates device record if new, updates last_seen if known.
    Returns {"device_id": int, "is_new": bool, "trusted": bool}.
    """
    fp = fingerprint(user_agent, ip_address)
    now = datetime.utcnow()

    existing = (
        session.query(TrustedDevice)
        .filter_by(user_id=uid, device_fingerprint=fp)
        .first()
    )

    if existing:
        existing.last_seen_at = now
        if ip_address:  # guard: never overwrite a known IP with None
            existing.ip_address = ip_address
        session.commit()
        logger.debug("Known device login user=%s device=%s", uid, existing.id)
        return {"device_id": existing.id, "is_new": False, "trusted": existing.trusted}

    # New device
    device = TrustedDevice(
        user_id=uid,
        device_fingerprint=fp,
        user_agent=(user_agent or "")[:500],
        ip_address=(ip_address or "")[:45],
        trusted=False,
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(device)
    session.commit()
    logger.info("New device seen user=%s device=%s ip=%s", uid, device.id, ip_address)
    return {"device_id": device.id, "is_new": True, "trusted": False}


def device_to_dict(device: TrustedDevice) -> dict:
    return {
        "id":                 device.id,
        "device_fingerprint": device.device_fingerprint[:12] + "...",  # truncated for privacy
        "user_agent":         device.user_agent,
        "ip_address":         device.ip_address,
        "device_name":        device.device_name,
        "trusted":            device.trusted,
        "first_seen_at":      device.first_seen_at.isoformat(),
        "last_seen_at":       device.last_seen_at.isoformat(),
    }
