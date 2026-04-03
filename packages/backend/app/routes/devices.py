"""Device trust management routes."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.device_trust import get_devices, trust_device, revoke_device, remove_device

bp = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


@bp.get("")
@jwt_required()
def list_devices():
    """List all known devices for the user."""
    uid = int(get_jwt_identity())
    return jsonify(get_devices(uid))


@bp.post("/<device_id>/trust")
@jwt_required()
def trust(device_id: str):
    uid = int(get_jwt_identity())
    if trust_device(uid, device_id):
        return jsonify(message="device trusted")
    return jsonify(error="device not found"), 404


@bp.post("/<device_id>/revoke")
@jwt_required()
def revoke(device_id: str):
    uid = int(get_jwt_identity())
    if revoke_device(uid, device_id):
        return jsonify(message="device revoked")
    return jsonify(error="device not found"), 404


@bp.delete("/<device_id>")
@jwt_required()
def delete_device(device_id: str):
    uid = int(get_jwt_identity())
    if remove_device(uid, device_id):
        return jsonify(message="device removed")
    return jsonify(error="device not found"), 404
