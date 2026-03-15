"""Routes for device trust management."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.device_trust import (
    register_device,
    recognize_device,
    get_user_devices,
    update_device,
    revoke_device,
    revoke_all_devices,
    delete_device,
    get_device_stats,
)

bp = Blueprint("device_trust", __name__)


@bp.route("/register", methods=["POST"])
@jwt_required()
def register_device_endpoint():
    """Register or update a trusted device.

    JSON body:
    - device_name: optional friendly name
    - trust_level: full | standard | limited (default: standard)
    - expires_days: days until expiry (default: 90, 0 = no expiry)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    user_agent = request.headers.get("User-Agent", "")
    ip_address = request.remote_addr or ""

    result = register_device(
        user_id=user_id,
        user_agent=user_agent,
        ip_address=ip_address,
        device_name=data.get("device_name"),
        trust_level=data.get("trust_level", "standard"),
        expires_days=data.get("expires_days", 90),
    )

    return jsonify(result), 201


@bp.route("/recognize", methods=["POST"])
@jwt_required()
def recognize_device_endpoint():
    """Check if the current device is recognized/trusted."""
    user_id = int(get_jwt_identity())
    user_agent = request.headers.get("User-Agent", "")
    ip_address = request.remote_addr or ""

    result = recognize_device(user_id, user_agent, ip_address)
    status = 200 if result["recognized"] else 404

    return jsonify(result), status


@bp.route("/devices", methods=["GET"])
@jwt_required()
def list_devices():
    """List all trusted devices for the current user."""
    user_id = int(get_jwt_identity())
    include_revoked = request.args.get("include_revoked", "false").lower() == "true"

    devices = get_user_devices(user_id, include_revoked=include_revoked)
    return jsonify({"devices": devices, "count": len(devices)}), 200


@bp.route("/devices/<int:device_id>", methods=["PATCH"])
@jwt_required()
def update_device_endpoint(device_id):
    """Update a device's name or trust level.

    JSON body:
    - device_name: new friendly name
    - trust_level: full | standard | limited
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    result = update_device(
        user_id=user_id,
        device_db_id=device_id,
        device_name=data.get("device_name"),
        trust_level=data.get("trust_level"),
    )

    if result is None:
        return jsonify({"error": "Device not found or invalid trust level"}), 404

    return jsonify(result), 200


@bp.route("/devices/<int:device_id>/revoke", methods=["POST"])
@jwt_required()
def revoke_device_endpoint(device_id):
    """Revoke trust for a specific device."""
    user_id = int(get_jwt_identity())

    if revoke_device(user_id, device_id):
        return jsonify({"message": "Device trust revoked"}), 200

    return jsonify({"error": "Device not found"}), 404


@bp.route("/devices/revoke-all", methods=["POST"])
@jwt_required()
def revoke_all_endpoint():
    """Revoke all devices except the current one.

    JSON body:
    - except_current: boolean (default true)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    except_current = data.get("except_current", True)

    count = revoke_all_devices(user_id, except_current=except_current)
    return jsonify({"message": f"{count} devices revoked", "count": count}), 200


@bp.route("/devices/<int:device_id>", methods=["DELETE"])
@jwt_required()
def delete_device_endpoint(device_id):
    """Permanently delete a device record."""
    user_id = int(get_jwt_identity())

    if delete_device(user_id, device_id):
        return jsonify({"message": "Device deleted"}), 200

    return jsonify({"error": "Device not found"}), 404


@bp.route("/stats", methods=["GET"])
@jwt_required()
def device_stats():
    """Get device trust statistics."""
    user_id = int(get_jwt_identity())
    stats = get_device_stats(user_id)
    return jsonify(stats), 200
