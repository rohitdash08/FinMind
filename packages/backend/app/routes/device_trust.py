from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.device_trust import list_devices, revoke_device, rename_device

bp = Blueprint("devices", __name__)

@bp.get("")
@jwt_required()
def get_devices():
    return jsonify(list_devices(int(get_jwt_identity())))

@bp.delete("/<fingerprint>")
@jwt_required()
def revoke(fingerprint):
    ok = revoke_device(int(get_jwt_identity()), fingerprint)
    return (jsonify({"revoked": True}), 200) if ok else (jsonify(error="not found"), 404)

@bp.patch("/<fingerprint>")
@jwt_required()
def rename(fingerprint):
    d = request.get_json() or {}
    name = d.get("name","").strip()
    if not name:
        return jsonify(error="name required"), 400
    ok = rename_device(int(get_jwt_identity()), fingerprint, name)
    return (jsonify({"renamed": True}), 200) if ok else (jsonify(error="not found"), 404)
