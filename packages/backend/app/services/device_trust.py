"""Device trust management & recognition service.

Tracks devices that log in to a user's account. Flags new/unknown
devices and allows users to trust or revoke devices.

Device fingerprinting uses: User-Agent + IP prefix (first 3 octets)
to create a stable device identifier without storing full IPs.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TypedDict

from ..extensions import db

logger = logging.getLogger("finmind.device_trust")


class DeviceInfo(TypedDict):
    device_id: str
    user_agent: str
    ip_prefix: str
    first_seen: str
    last_seen: str
    trusted: bool
    login_count: int


# We use the existing db models pattern - store in a new table
# For now, use a simple in-memory + redis approach
from ..extensions import redis_client
import json


def _device_key(user_id: int) -> str:
    return f"user:{user_id}:devices"


def _make_device_id(user_agent: str, ip: str) -> str:
    """Create a stable device fingerprint."""
    ip_prefix = ".".join(ip.split(".")[:3]) if "." in ip else ip[:8]
    raw = f"{user_agent}:{ip_prefix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def record_login(user_id: int, user_agent: str, ip: str) -> tuple[DeviceInfo, bool]:
    """Record a device login. Returns (device_info, is_new_device)."""
    device_id = _make_device_id(user_agent, ip)
    ip_prefix = ".".join(ip.split(".")[:3]) if "." in ip else ip[:8]
    now = datetime.now(timezone.utc).isoformat()

    key = _device_key(user_id)
    existing = _get_device(user_id, device_id)

    if existing:
        existing["last_seen"] = now
        existing["login_count"] = existing.get("login_count", 0) + 1
        _save_device(user_id, device_id, existing)
        return existing, False
    else:
        device = DeviceInfo(
            device_id=device_id,
            user_agent=user_agent[:200],
            ip_prefix=ip_prefix,
            first_seen=now,
            last_seen=now,
            trusted=False,
            login_count=1,
        )
        _save_device(user_id, device_id, device)
        logger.info("New device detected user=%s device=%s", user_id, device_id)
        return device, True


def get_devices(user_id: int) -> list[DeviceInfo]:
    """Get all known devices for a user."""
    key = _device_key(user_id)
    try:
        raw = redis_client.hgetall(key)
        devices = [json.loads(v) for v in raw.values()]
        devices.sort(key=lambda d: d.get("last_seen", ""), reverse=True)
        return devices
    except Exception:
        return []


def trust_device(user_id: int, device_id: str) -> bool:
    """Mark a device as trusted."""
    device = _get_device(user_id, device_id)
    if not device:
        return False
    device["trusted"] = True
    _save_device(user_id, device_id, device)
    return True


def revoke_device(user_id: int, device_id: str) -> bool:
    """Revoke trust for a device."""
    device = _get_device(user_id, device_id)
    if not device:
        return False
    device["trusted"] = False
    _save_device(user_id, device_id, device)
    return True


def remove_device(user_id: int, device_id: str) -> bool:
    """Remove a device entirely."""
    key = _device_key(user_id)
    try:
        return redis_client.hdel(key, device_id) > 0
    except Exception:
        return False


def _get_device(user_id: int, device_id: str) -> DeviceInfo | None:
    key = _device_key(user_id)
    try:
        raw = redis_client.hget(key, device_id)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _save_device(user_id: int, device_id: str, device: DeviceInfo):
    key = _device_key(user_id)
    try:
        redis_client.hset(key, device_id, json.dumps(device))
    except Exception:
        logger.warning("Failed to save device info user=%s", user_id)
