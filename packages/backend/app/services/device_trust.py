"""
Device trust management & recognition (issue #125).
Users can view, name, and revoke trusted devices.
"""
import hashlib, json, logging, secrets
from datetime import datetime, timezone
from ..extensions import db, redis_client

logger = logging.getLogger("finmind.devices")
DEVICE_TTL = 60 * 60 * 24 * 90   # 90 days
TRUST_PREFIX = "trust:devices:"


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _fp(user_agent: str, ip: str) -> str:
    raw = f"{user_agent}|{'.'.join(ip.split('.')[:2])}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _store_key(user_id: int) -> str:
    return f"{TRUST_PREFIX}{user_id}"


def register_device(user_id: int, user_agent: str, ip: str,
                    name: str = None) -> dict:
    """Register a device fingerprint as trusted. Returns device record."""
    fp = _fp(user_agent, ip)
    key = _store_key(user_id)
    raw = redis_client.hget(key, fp)
    if raw:
        return json.loads(raw)  # already known
    device = {
        "fingerprint": fp, "name": name or _auto_name(user_agent),
        "user_agent": user_agent[:200], "ip_prefix": '.'.join(ip.split('.')[:2]),
        "first_seen": _utcnow(), "last_seen": _utcnow(), "trusted": True,
    }
    redis_client.hset(key, fp, json.dumps(device))
    redis_client.expire(key, DEVICE_TTL)
    logger.info("New device registered user=%d fp=%s", user_id, fp)
    return device


def is_trusted(user_id: int, user_agent: str, ip: str) -> bool:
    fp = _fp(user_agent, ip)
    raw = redis_client.hget(_store_key(user_id), fp)
    if not raw:
        return False
    device = json.loads(raw)
    if not device.get("trusted"):
        return False
    # Update last_seen
    device["last_seen"] = _utcnow()
    redis_client.hset(_store_key(user_id), fp, json.dumps(device))
    return True


def list_devices(user_id: int) -> list:
    raw = redis_client.hgetall(_store_key(user_id))
    devices = [json.loads(v) for v in raw.values()]
    return sorted(devices, key=lambda d: d.get("last_seen", ""), reverse=True)


def revoke_device(user_id: int, fingerprint: str) -> bool:
    key = _store_key(user_id)
    raw = redis_client.hget(key, fingerprint)
    if not raw:
        return False
    device = json.loads(raw)
    device["trusted"] = False
    redis_client.hset(key, fingerprint, json.dumps(device))
    logger.warning("Device revoked user=%d fp=%s", user_id, fingerprint)
    return True


def rename_device(user_id: int, fingerprint: str, name: str) -> bool:
    key = _store_key(user_id)
    raw = redis_client.hget(key, fingerprint)
    if not raw:
        return False
    device = json.loads(raw)
    device["name"] = name[:100]
    redis_client.hset(key, fingerprint, json.dumps(device))
    return True


def _auto_name(user_agent: str) -> str:
    ua = user_agent.lower()
    if "iphone" in ua: return "iPhone"
    if "ipad" in ua: return "iPad"
    if "android" in ua: return "Android Device"
    if "mac" in ua: return "Mac"
    if "windows" in ua: return "Windows PC"
    if "linux" in ua: return "Linux Device"
    return "Unknown Device"
