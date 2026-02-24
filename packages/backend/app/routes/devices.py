"""
devices.py — Device trust management endpoints.

GET    /devices                   — list all devices for the current user
PATCH  /devices/<id>/name         — set a friendly name for a device
POST   /devices/<id>/trust        — mark a device as trusted
POST   /devices/<id>/revoke       — remove trusted status
DELETE /devices/<id>              — forget a device
"""
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import TrustedDevice
from ..services.device_trust import device_to_dict

bp_devices = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


@bp_devices.get("")
@jwt_required()
def list_devices():
    uid = int(get_jwt_identity())
    devices = (
        db.session.query(TrustedDevice)
        .filter_by(user_id=uid)
        .order_by(TrustedDevice.last_seen_at.desc())
        .all()
    )
    return jsonify([device_to_dict(d) for d in devices])


@bp_devices.patch("/<int:device_id>/name")
@jwt_required()
def set_device_name(device_id: int):
    uid = int(get_jwt_identity())
    device = db.session.get(TrustedDevice, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()[:100]
    if not name:
        return jsonify(error="name required"), 400
    device.device_name = name
    db.session.commit()
    return jsonify(device_to_dict(device))


@bp_devices.post("/<int:device_id>/trust")
@jwt_required()
def trust_device(device_id: int):
    uid = int(get_jwt_identity())
    device = db.session.get(TrustedDevice, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="not found"), 404
    device.trusted = True
    db.session.commit()
    logger.info("Device trusted user=%s device=%s", uid, device_id)
    return jsonify(device_to_dict(device))


@bp_devices.post("/<int:device_id>/revoke")
@jwt_required()
def revoke_device(device_id: int):
    uid = int(get_jwt_identity())
    device = db.session.get(TrustedDevice, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="not found"), 404
    device.trusted = False
    db.session.commit()
    logger.info("Device revoked user=%s device=%s", uid, device_id)
    return jsonify(device_to_dict(device))


@bp_devices.delete("/<int:device_id>")
@jwt_required()
def forget_device(device_id: int):
    uid = int(get_jwt_identity())
    device = db.session.get(TrustedDevice, device_id)
    if not device or device.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(device)
    db.session.commit()
    logger.info("Device forgotten user=%s device=%s", uid, device_id)
    return jsonify(message="device forgotten")
