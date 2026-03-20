"""Device trust management & recognition (Issue #125)."""

import hashlib
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import DeviceFingerprint

bp = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


def _compute_device_hash(user_agent: str, ip_address: str) -> str:
    """Generate a deterministic fingerprint hash from user-agent + IP."""
    raw = f"{user_agent}|{ip_address}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _device_name_from_ua(user_agent: str) -> str:
    """Extract a human-friendly device name from the User-Agent string."""
    ua = user_agent or "Unknown Device"
    # Simple heuristic: take the first segment before '('
    if "(" in ua:
        platform = ua.split("(")[1].split(")")[0] if "(" in ua else ""
        # Try to find browser name
        browser = ""
        for token in ("Chrome", "Firefox", "Safari", "Edge", "Opera"):
            if token in ua:
                browser = token
                break
        if browser and platform:
            return f"{browser} on {platform}"
        if platform:
            return platform
    if len(ua) > 80:
        return ua[:80]
    return ua


def record_device_on_login(user_id: int) -> None:
    """Called during login to record/update the device fingerprint."""
    user_agent = request.headers.get("User-Agent", "")
    ip_address = request.remote_addr or "unknown"
    device_hash = _compute_device_hash(user_agent, ip_address)

    existing = (
        db.session.query(DeviceFingerprint)
        .filter_by(user_id=user_id, device_hash=device_hash)
        .first()
    )
    if existing:
        existing.last_seen = datetime.utcnow()
        db.session.commit()
        return

    device = DeviceFingerprint(
        user_id=user_id,
        device_hash=device_hash,
        device_name=_device_name_from_ua(user_agent),
        ip_address=ip_address,
        trusted=False,
    )
    db.session.add(device)
    db.session.commit()
    logger.info("New device recorded user=%s hash=%s", user_id, device_hash[:12])


@bp.get("")
@jwt_required()
def list_devices():
    """List all devices for the authenticated user."""
    uid = int(get_jwt_identity())
    devices = (
        db.session.query(DeviceFingerprint)
        .filter_by(user_id=uid)
        .order_by(DeviceFingerprint.last_seen.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": d.id,
                "device_name": d.device_name,
                "device_hash": d.device_hash[:12] + "...",
                "ip_address": d.ip_address,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "trusted": d.trusted,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in devices
        ]
    )


@bp.post("/trust")
@jwt_required()
def trust_device():
    """Mark a device as trusted."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify(error="device_id required"), 400

    device = db.session.get(DeviceFingerprint, int(device_id))
    if not device or device.user_id != uid:
        return jsonify(error="not found"), 404

    device.trusted = True
    db.session.commit()
    logger.info("Device trusted user=%s device_id=%s", uid, device_id)
    return jsonify(message="device trusted")


@bp.delete("/<int:device_id>")
@jwt_required()
def remove_device(device_id: int):
    """Remove a device fingerprint."""
    uid = int(get_jwt_identity())
    device = db.session.get(DeviceFingerprint, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(device)
    db.session.commit()
    logger.info("Device removed user=%s device_id=%s", uid, device_id)
    return jsonify(message="device removed")
