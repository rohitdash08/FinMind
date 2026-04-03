"""Routes for Device Trust Management (issue #125)."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.device_trust import (
    register_device,
    verify_device_token,
    revoke_device,
    revoke_all_devices,
    get_user_devices,
    recognize_device,
)

bp = Blueprint("device_trust", __name__)


@bp.route("/devices", methods=["GET"])
@jwt_required()
def list_devices():
    """List trusted devices for the current user."""
    user_id = int(get_jwt_identity())
    include_revoked = request.args.get("include_revoked", "false").lower() == "true"
    devices = get_user_devices(user_id, include_revoked=include_revoked)
    return jsonify({"devices": devices, "count": len(devices)}), 200


@bp.route("/devices", methods=["POST"])
@jwt_required()
def add_device():
    """Register a new trusted device."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    device_name = (data.get("device_name") or "").strip()
    if not device_name:
        return jsonify({"error": "device_name is required"}), 400

    trust_days = data.get("trust_days", 30)
    try:
        trust_days = int(trust_days) if trust_days is not None else None
    except (ValueError, TypeError):
        return jsonify({"error": "trust_days must be an integer or null"}), 400

    user_agent = request.headers.get("User-Agent") or data.get("user_agent")
    ip_address = request.remote_addr or data.get("ip_address")

    device = register_device(
        user_id=user_id,
        device_name=device_name,
        user_agent=user_agent,
        ip_address=ip_address,
        trust_days=trust_days,
    )
    return jsonify(device.to_dict()), 201


@bp.route("/devices/<int:device_id>", methods=["DELETE"])
@jwt_required()
def revoke_device_route(device_id: int):
    """Revoke trust for a specific device."""
    user_id = int(get_jwt_identity())
    device = revoke_device(device_id=device_id, user_id=user_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    return jsonify({"message": "Device trust revoked", "device": device.to_dict()}), 200


@bp.route("/devices/revoke-all", methods=["POST"])
@jwt_required()
def revoke_all_route():
    """Revoke all trusted devices (except current if token provided)."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    except_token = data.get("except_token")
    count = revoke_all_devices(user_id=user_id, except_token=except_token)
    return jsonify({"revoked_count": count, "message": f"Revoked {count} device(s)"}), 200


@bp.route("/devices/verify", methods=["POST"])
@jwt_required()
def verify_device():
    """Verify a device token and mark device as seen."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    token = data.get("device_token", "")
    if not token:
        return jsonify({"error": "device_token is required"}), 400
    device = verify_device_token(token=token, user_id=user_id)
    if not device:
        return jsonify({"trusted": False, "message": "Device not recognized or expired"}), 200
    return jsonify({"trusted": True, "device": device.to_dict()}), 200


@bp.route("/devices/recognize", methods=["POST"])
@jwt_required()
def recognize_device_route():
    """Auto-recognize a device by fingerprint (user-agent + IP)."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    user_agent = request.headers.get("User-Agent") or data.get("user_agent")
    ip_address = request.remote_addr or data.get("ip_address")
    device = recognize_device(user_id=user_id, user_agent=user_agent, ip_address=ip_address)
    if not device:
        return jsonify({"recognized": False}), 200
    return jsonify({"recognized": True, "device": device.to_dict()}), 200