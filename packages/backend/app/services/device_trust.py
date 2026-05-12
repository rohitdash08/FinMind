"""Device trust management & recognition."""

import hashlib
import json
from datetime import datetime

from ..extensions import db, redis_client
import logging

logger = logging.getLogger("finmind.device_trust")

DEVICES_KEY = "devices:{user_id}"
MAX_DEVICES = 10


def generate_device_fingerprint(user_agent: str, ip: str) -> str:
    """Generate a device fingerprint from user agent and IP prefix."""
    # Use IP prefix (first 3 octets) for some stability
    ip_prefix = ".".join(ip.split(".")[:3]) if "." in ip else ip[:8]
    raw = f"{user_agent}|{ip_prefix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def register_device(user_id: int, user_agent: str, ip: str) -> dict:
    """Register or update a device for a user. Returns device info."""
    fingerprint = generate_device_fingerprint(user_agent, ip)
    key = DEVICES_KEY.format(user_id=user_id)

    # Check if device already known
    existing = redis_client.hget(key, fingerprint)
    if existing:
        device = json.loads(existing)
        device["last_seen"] = datetime.utcnow().isoformat()
        device["login_count"] = device.get("login_count", 0) + 1
        redis_client.hset(key, fingerprint, json.dumps(device))
        return {"device": device, "is_new": False}

    # New device
    device = {
        "fingerprint": fingerprint,
        "user_agent": user_agent[:200],
        "ip_prefix": ".".join(ip.split(".")[:3]) if "." in ip else ip[:8],
        "trusted": False,
        "first_seen": datetime.utcnow().isoformat(),
        "last_seen": datetime.utcnow().isoformat(),
        "login_count": 1,
    }

    # Limit devices
    if redis_client.hlen(key) >= MAX_DEVICES:
        # Remove oldest
        all_devices = redis_client.hgetall(key)
        oldest_fp = min(all_devices, key=lambda fp: json.loads(all_devices[fp]).get("last_seen", ""))
        redis_client.hdel(key, oldest_fp)

    redis_client.hset(key, fingerprint, json.dumps(device))
    redis_client.expire(key, 86400 * 365)  # 1 year

    return {"device": device, "is_new": True}


def get_devices(user_id: int) -> list[dict]:
    """Get all known devices for a user."""
    key = DEVICES_KEY.format(user_id=user_id)
    all_devices = redis_client.hgetall(key)
    return [json.loads(v) for v in all_devices.values()]


def trust_device(user_id: int, fingerprint: str) -> bool:
    """Mark a device as trusted."""
    key = DEVICES_KEY.format(user_id=user_id)
    raw = redis_client.hget(key, fingerprint)
    if not raw:
        return False
    device = json.loads(raw)
    device["trusted"] = True
    redis_client.hset(key, fingerprint, json.dumps(device))
    return True


def revoke_device(user_id: int, fingerprint: str) -> bool:
    """Remove a device from trusted list."""
    key = DEVICES_KEY.format(user_id=user_id)
    return redis_client.hdel(key, fingerprint) > 0


def is_trusted_device(user_id: int, user_agent: str, ip: str) -> bool:
    """Check if current device is trusted."""
    fingerprint = generate_device_fingerprint(user_agent, ip)
    key = DEVICES_KEY.format(user_id=user_id)
    raw = redis_client.hget(key, fingerprint)
    if not raw:
        return False
    device = json.loads(raw)
    return device.get("trusted", False)
