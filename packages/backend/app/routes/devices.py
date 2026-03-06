from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import TrustedDevice
from datetime import datetime
import logging

bp = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


@bp.get("/")
@jwt_required()
def list_devices():
    """List all devices for the current user."""
    uid = int(get_jwt_identity())
    devices = (
        db.session.query(TrustedDevice)
        .filter_by(user_id=uid)
        .order_by(TrustedDevice.last_seen.desc())
        .all()
    )
    return jsonify(
        [
            _device_to_dict(d)
            for d in devices
        ]
    )


@bp.get("/current")
@jwt_required()
def current_device():
    """Get or create the current device record based on request fingerprint."""
    uid = int(get_jwt_identity())
    user_agent = request.headers.get("User-Agent", "")
    ip_address = request.remote_addr or "unknown"
    fingerprint = TrustedDevice.generate_fingerprint(user_agent, ip_address)

    device = (
        db.session.query(TrustedDevice)
        .filter_by(user_id=uid, device_fingerprint=fingerprint)
        .first()
    )
    if not device:
        device = TrustedDevice(
            user_id=uid,
            device_fingerprint=fingerprint,
            device_name=_extract_device_name(user_agent),
            ip_address=ip_address,
            user_agent=user_agent,
            is_trusted=False,
        )
        db.session.add(device)
        db.session.commit()
        logger.info("New device recorded for user_id=%s fp=%s", uid, fingerprint[:12])
    else:
        device.last_seen = datetime.utcnow()
        db.session.commit()

    return jsonify(_device_to_dict(device))


@bp.post("/trust")
@jwt_required()
def trust_device():
    """Mark a device as trusted."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify(error="device_id required"), 400

    device = db.session.query(TrustedDevice).filter_by(
        id=device_id, user_id=uid
    ).first()
    if not device:
        return jsonify(error="device not found"), 404

    device.is_trusted = True
    db.session.commit()
    logger.info("Device id=%s trusted by user_id=%s", device_id, uid)
    return jsonify(_device_to_dict(device))


@bp.delete("/<int:device_id>")
@jwt_required()
def remove_device(device_id: int):
    """Remove/revoke a trusted device."""
    uid = int(get_jwt_identity())
    device = db.session.query(TrustedDevice).filter_by(
        id=device_id, user_id=uid
    ).first()
    if not device:
        return jsonify(error="device not found"), 404

    db.session.delete(device)
    db.session.commit()
    logger.info("Device id=%s removed by user_id=%s", device_id, uid)
    return jsonify(message="device removed"), 200


def _device_to_dict(device: TrustedDevice) -> dict:
    return {
        "id": device.id,
        "device_fingerprint": device.device_fingerprint,
        "device_name": device.device_name,
        "ip_address": device.ip_address,
        "is_trusted": device.is_trusted,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "created_at": device.created_at.isoformat() if device.created_at else None,
    }


def _extract_device_name(user_agent: str) -> str:
    """Extract a human-readable device name from the User-Agent string."""
    if not user_agent:
        return "Unknown Device"
    ua_lower = user_agent.lower()
    if "mobile" in ua_lower or "android" in ua_lower:
        return "Mobile Device"
    if "iphone" in ua_lower or "ipad" in ua_lower:
        return "iOS Device"
    if "macintosh" in ua_lower or "mac os" in ua_lower:
        return "Mac"
    if "windows" in ua_lower:
        return "Windows PC"
    if "linux" in ua_lower:
        return "Linux PC"
    return "Unknown Device"
