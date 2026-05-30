import hashlib
import json
import logging
from datetime import datetime

from flask import request

from ..extensions import db
from ..models import Device

logger = logging.getLogger("finmind.device_trust")

FINGERPRINT_SOURCE_KEYS = [
    "user_agent",
    "accept_language",
    "ip",
]


def compute_fingerprint(
    user_agent: str | None = None,
    ip_address: str | None = None,
    accept_language: str | None = None,
) -> str:
    raw = json.dumps(
        {
            "ua": (user_agent or "").strip(),
            "ip": (ip_address or "").strip(),
            "al": (accept_language or "").strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_trust_score(user_id: int, ip_address: str | None, include_pending: bool = False) -> int:
    if not ip_address:
        return 0
    count = (
        db.session.query(Device.id)
        .filter(Device.user_id == user_id, Device.ip_address == ip_address)
        .count()
    )
    total = count + (1 if include_pending else 0)
    return min(total * 25, 100)


def register_device(
    user_id: int,
    user_agent: str | None = None,
    ip_address: str | None = None,
    accept_language: str | None = None,
) -> Device:
    fingerprint = compute_fingerprint(user_agent, ip_address, accept_language)
    existing = (
        db.session.query(Device)
        .filter(Device.user_id == user_id, Device.fingerprint == fingerprint)
        .first()
    )
    if existing:
        existing.last_seen_at = datetime.utcnow()
        existing.user_agent = user_agent
        existing.ip_address = ip_address
        existing.accept_language = accept_language
        existing.trust_score = compute_trust_score(user_id, ip_address)
        db.session.commit()
        logger.info("Updated device id=%s user=%s score=%s", existing.id, user_id, existing.trust_score)
        return existing

    score = compute_trust_score(user_id, ip_address, include_pending=True)
    device = Device(
        user_id=user_id,
        fingerprint=fingerprint,
        user_agent=user_agent,
        ip_address=ip_address,
        accept_language=accept_language,
        trust_score=score,
        last_seen_at=datetime.utcnow(),
    )
    db.session.add(device)
    db.session.commit()
    logger.info("Registered new device id=%s user=%s score=%s", device.id, user_id, score)
    return device


def is_new_device(user_id: int, fingerprint: str) -> bool:
    return (
        db.session.query(Device.id)
        .filter(Device.user_id == user_id, Device.fingerprint == fingerprint)
        .first()
        is None
    )


def list_devices(user_id: int) -> list[dict]:
    items = (
        db.session.query(Device)
        .filter(Device.user_id == user_id)
        .order_by(Device.last_seen_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "user_agent": d.user_agent,
            "ip_address": d.ip_address,
            "trust_score": d.trust_score,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in items
    ]


def remove_device(device_id: int, user_id: int) -> bool:
    device = db.session.get(Device, device_id)
    if not device or device.user_id != user_id:
        return False
    db.session.delete(device)
    db.session.commit()
    logger.info("Removed device id=%s user=%s", device_id, user_id)
    return True


def request_device_info() -> dict:
    return {
        "user_agent": request.headers.get("User-Agent", ""),
        "ip_address": request.remote_addr or request.headers.get("X-Forwarded-For", ""),
        "accept_language": request.headers.get("Accept-Language", ""),
    }
