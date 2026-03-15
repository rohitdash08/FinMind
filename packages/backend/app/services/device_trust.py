"""Device trust management and recognition service.

Provides:
- Device fingerprinting and registration
- Trust level management (full, standard, limited)
- Device activity tracking
- Trust revocation and expiration
- Device recognition for login flows
"""

import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models import TrustedDevice


# ─── Device Fingerprinting ──────────────────────────────────────────


def generate_device_id(user_agent: str, ip_address: str = "",
                       extra: str = "") -> str:
    """Generate a deterministic device fingerprint.

    Combines user-agent, IP prefix, and optional extra data.
    """
    # Use first 3 octets of IP for stability (ignore last octet changes)
    ip_prefix = ".".join(ip_address.split(".")[:3]) if ip_address else ""
    raw = f"{user_agent}|{ip_prefix}|{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def parse_user_agent(user_agent: str) -> dict:
    """Extract device info from User-Agent string.

    Returns dict with device_type, browser, os.
    """
    ua = user_agent.lower() if user_agent else ""

    # Detect device type
    if any(k in ua for k in ("mobile", "android", "iphone", "ipad")):
        if "ipad" in ua or "tablet" in ua:
            device_type = "tablet"
        else:
            device_type = "mobile"
    else:
        device_type = "desktop"

    # Detect browser
    browser = "Unknown"
    if "firefox" in ua:
        browser = "Firefox"
    elif "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua:
        browser = "Chrome"
    elif "safari" in ua:
        browser = "Safari"
    elif "opera" in ua or "opr" in ua:
        browser = "Opera"

    # Detect OS (check mobile-specific first to avoid false matches)
    os_name = "Unknown"
    if "iphone" in ua or "ipad" in ua:
        os_name = "iOS"
    elif "android" in ua:
        os_name = "Android"
    elif "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"

    return {"device_type": device_type, "browser": browser, "os": os_name}


# ─── Device Registration ────────────────────────────────────────────


def register_device(user_id: int, user_agent: str,
                    ip_address: str = "",
                    device_name: str | None = None,
                    trust_level: str = "standard",
                    expires_days: int = 90) -> dict:
    """Register or update a trusted device.

    Args:
        user_id: User ID
        user_agent: HTTP User-Agent header
        ip_address: Client IP address
        device_name: Optional friendly name
        trust_level: full, standard, or limited
        expires_days: Days until trust expires (0 = no expiry)

    Returns:
        Dict with device info
    """
    device_id = generate_device_id(user_agent, ip_address)
    ua_info = parse_user_agent(user_agent)

    # Check if device already exists
    existing = TrustedDevice.query.filter_by(
        user_id=user_id, device_id=device_id
    ).first()

    if existing:
        # Update existing device
        existing.last_active_at = datetime.utcnow()
        existing.ip_address = ip_address
        existing.is_current = True
        existing.revoked = False
        existing.revoked_at = None
        if device_name:
            existing.device_name = device_name
        if trust_level:
            existing.trust_level = trust_level
        db.session.commit()
        return _device_to_dict(existing)

    # Reset is_current on other devices
    TrustedDevice.query.filter_by(user_id=user_id, is_current=True).update(
        {"is_current": False}
    )

    # Create new device
    expires_at = (datetime.utcnow() + timedelta(days=expires_days)
                  if expires_days > 0 else None)

    device = TrustedDevice(
        user_id=user_id,
        device_id=device_id,
        device_name=device_name or f"{ua_info['browser']} on {ua_info['os']}",
        device_type=ua_info["device_type"],
        browser=ua_info["browser"],
        os=ua_info["os"],
        ip_address=ip_address,
        trust_level=trust_level,
        is_current=True,
        last_active_at=datetime.utcnow(),
        expires_at=expires_at,
    )
    db.session.add(device)
    db.session.commit()

    return _device_to_dict(device)


def recognize_device(user_id: int, user_agent: str,
                     ip_address: str = "") -> dict:
    """Check if a device is recognized/trusted.

    Args:
        user_id: User ID
        user_agent: HTTP User-Agent header
        ip_address: Client IP address

    Returns:
        Dict with recognition status and device info if found
    """
    device_id = generate_device_id(user_agent, ip_address)

    device = TrustedDevice.query.filter_by(
        user_id=user_id, device_id=device_id
    ).first()

    if not device:
        return {"recognized": False, "device": None, "reason": "unknown_device"}

    if device.revoked:
        return {"recognized": False, "device": _device_to_dict(device),
                "reason": "device_revoked"}

    if device.expires_at and device.expires_at < datetime.utcnow():
        return {"recognized": False, "device": _device_to_dict(device),
                "reason": "trust_expired"}

    # Update activity
    device.last_active_at = datetime.utcnow()
    device.ip_address = ip_address
    db.session.commit()

    return {
        "recognized": True,
        "device": _device_to_dict(device),
        "trust_level": device.trust_level,
    }


# ─── Device Management ──────────────────────────────────────────────


def get_user_devices(user_id: int, include_revoked: bool = False) -> list[dict]:
    """Get all trusted devices for a user.

    Args:
        user_id: User ID
        include_revoked: Whether to include revoked devices

    Returns:
        List of device dicts
    """
    query = TrustedDevice.query.filter_by(user_id=user_id)
    if not include_revoked:
        query = query.filter_by(revoked=False)

    devices = query.order_by(TrustedDevice.last_active_at.desc()).all()
    return [_device_to_dict(d) for d in devices]


def update_device(user_id: int, device_db_id: int,
                  device_name: str | None = None,
                  trust_level: str | None = None) -> dict | None:
    """Update device properties.

    Args:
        user_id: User ID (authorization)
        device_db_id: Database ID of the device
        device_name: New friendly name
        trust_level: New trust level

    Returns:
        Updated device dict or None if not found
    """
    device = TrustedDevice.query.filter_by(
        id=device_db_id, user_id=user_id
    ).first()

    if not device:
        return None

    if device_name is not None:
        device.device_name = device_name
    if trust_level is not None:
        if trust_level not in ("full", "standard", "limited"):
            return None
        device.trust_level = trust_level

    device.updated_at = datetime.utcnow()
    db.session.commit()

    return _device_to_dict(device)


def revoke_device(user_id: int, device_db_id: int) -> bool:
    """Revoke trust for a device.

    Args:
        user_id: User ID (authorization)
        device_db_id: Database ID of the device

    Returns:
        True if revoked, False if not found
    """
    device = TrustedDevice.query.filter_by(
        id=device_db_id, user_id=user_id
    ).first()

    if not device:
        return False

    device.revoked = True
    device.revoked_at = datetime.utcnow()
    device.is_current = False
    db.session.commit()

    return True


def revoke_all_devices(user_id: int, except_current: bool = True) -> int:
    """Revoke all trusted devices for a user.

    Args:
        user_id: User ID
        except_current: Keep the current device trusted

    Returns:
        Number of devices revoked
    """
    query = TrustedDevice.query.filter_by(user_id=user_id, revoked=False)
    if except_current:
        query = query.filter_by(is_current=False)

    devices = query.all()
    count = 0
    for d in devices:
        d.revoked = True
        d.revoked_at = datetime.utcnow()
        d.is_current = False
        count += 1

    db.session.commit()
    return count


def delete_device(user_id: int, device_db_id: int) -> bool:
    """Permanently delete a device record.

    Args:
        user_id: User ID (authorization)
        device_db_id: Database ID

    Returns:
        True if deleted, False if not found
    """
    device = TrustedDevice.query.filter_by(
        id=device_db_id, user_id=user_id
    ).first()

    if not device:
        return False

    db.session.delete(device)
    db.session.commit()
    return True


def get_device_stats(user_id: int) -> dict:
    """Get device trust statistics for a user.

    Returns:
        Dict with counts and breakdown
    """
    all_devices = TrustedDevice.query.filter_by(user_id=user_id).all()

    total = len(all_devices)
    active = sum(1 for d in all_devices if not d.revoked)
    revoked = sum(1 for d in all_devices if d.revoked)
    expired = sum(
        1 for d in all_devices
        if d.expires_at and d.expires_at < datetime.utcnow() and not d.revoked
    )

    by_type = {}
    by_trust = {}
    for d in all_devices:
        if not d.revoked:
            by_type[d.device_type] = by_type.get(d.device_type, 0) + 1
            by_trust[d.trust_level] = by_trust.get(d.trust_level, 0) + 1

    return {
        "total": total,
        "active": active,
        "revoked": revoked,
        "expired": expired,
        "by_type": by_type,
        "by_trust_level": by_trust,
    }


# ─── Helpers ─────────────────────────────────────────────────────────


def _device_to_dict(device: TrustedDevice) -> dict:
    """Convert TrustedDevice model to dict."""
    return {
        "id": device.id,
        "device_id": device.device_id,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "browser": device.browser,
        "os": device.os,
        "ip_address": device.ip_address,
        "location": device.location,
        "trust_level": device.trust_level,
        "is_current": device.is_current,
        "last_active_at": device.last_active_at.isoformat() if device.last_active_at else None,
        "trusted_at": device.trusted_at.isoformat() if device.trusted_at else None,
        "expires_at": device.expires_at.isoformat() if device.expires_at else None,
        "revoked": device.revoked,
        "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
    }
