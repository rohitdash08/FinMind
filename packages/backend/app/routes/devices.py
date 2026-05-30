import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.device_trust import (
    list_devices,
    register_device,
    remove_device,
    request_device_info,
)

bp = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


@bp.get("")
@jwt_required()
def list_trusted_devices():
    uid = int(get_jwt_identity())
    devices = list_devices(uid)
    logger.info("List devices user=%s count=%s", uid, len(devices))
    return jsonify(devices)


@bp.post("")
@jwt_required()
def register_trusted_device():
    uid = int(get_jwt_identity())
    info = request_device_info()
    data = request.get_json(silent=True) or {}
    device = register_device(
        user_id=uid,
        user_agent=data.get("user_agent") or info.get("user_agent"),
        ip_address=data.get("ip_address") or info.get("ip_address"),
        accept_language=data.get("accept_language") or info.get("accept_language"),
    )
    return jsonify(
        id=device.id,
        trust_score=device.trust_score,
        last_seen_at=device.last_seen_at.isoformat() if device.last_seen_at else None,
    ), 201


@bp.delete("/<int:device_id>")
@jwt_required()
def remove_trusted_device(device_id: int):
    uid = int(get_jwt_identity())
    if not remove_device(device_id, uid):
        return jsonify(error="not found"), 404
    return jsonify(message="removed"), 200
