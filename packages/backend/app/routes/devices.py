from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import TrustedDevice
import hashlib
import logging

bp = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


def _make_fingerprint(user_agent: str, ip: str) -> str:
    raw = f"{user_agent}|{ip}"
    return hashlib.sha256(raw.encode()).hexdigest()


@bp.get("/")
@jwt_required()
def list_devices():
    uid = int(get_jwt_identity())
    devices = (
        db.session.query(TrustedDevice)
        .filter_by(user_id=uid)
        .order_by(TrustedDevice.last_seen_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": d.id,
                "device_name": d.device_name,
                "trusted": d.trusted,
                "user_agent": d.user_agent,
                "ip_address": d.ip_address,
                "last_seen_at": d.last_seen_at.isoformat() + "Z",
                "created_at": d.created_at.isoformat() + "Z",
            }
            for d in devices
        ]
    )


@bp.post("/")
@jwt_required()
def trust_device():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    device_name = (data.get("device_name") or "").strip()
    if not device_name:
        return jsonify(error="device_name is required"), 400

    user_agent = request.headers.get("User-Agent", "")
    ip = request.remote_addr or ""
    fingerprint = _make_fingerprint(user_agent, ip)

    existing = (
        db.session.query(TrustedDevice)
        .filter_by(user_id=uid, device_fingerprint=fingerprint)
        .first()
    )
    if existing:
        existing.trusted = True
        existing.device_name = device_name
        existing.last_seen_at = db.func.now()
        db.session.commit()
        logger.info("Re-trusted device id=%s for user_id=%s", existing.id, uid)
        return jsonify(
            id=existing.id,
            device_name=existing.device_name,
            trusted=existing.trusted,
            message="device re-trusted",
        ), 200

    device = TrustedDevice(
        user_id=uid,
        device_name=device_name,
        device_fingerprint=fingerprint,
        user_agent=user_agent,
        ip_address=ip,
        trusted=True,
    )
    db.session.add(device)
    db.session.commit()
    logger.info("Trusted new device id=%s for user_id=%s", device.id, uid)
    return jsonify(
        id=device.id,
        device_name=device.device_name,
        trusted=device.trusted,
        message="device trusted",
    ), 201


@bp.delete("/<int:device_id>")
@jwt_required()
def revoke_device(device_id: int):
    uid = int(get_jwt_identity())
    device = db.session.get(TrustedDevice, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="device not found"), 404
    device.trusted = False
    db.session.commit()
    logger.info("Revoked device id=%s for user_id=%s", device_id, uid)
    return jsonify(message="device revoked", id=device.id, trusted=False), 200


@bp.patch("/<int:device_id>")
@jwt_required()
def rename_device(device_id: int):
    uid = int(get_jwt_identity())
    device = db.session.get(TrustedDevice, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="device not found"), 404
    data = request.get_json() or {}
    new_name = (data.get("device_name") or "").strip()
    if not new_name:
        return jsonify(error="device_name is required"), 400
    device.device_name = new_name
    db.session.commit()
    logger.info("Renamed device id=%s to '%s' for user_id=%s", device_id, new_name, uid)
    return jsonify(id=device.id, device_name=device.device_name, trusted=device.trusted), 200
