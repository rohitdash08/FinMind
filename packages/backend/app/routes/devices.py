import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("devices", __name__)
logger = logging.getLogger("finmind.devices")


@bp.get("")
@jwt_required()
def list_trusted_devices():
    uid = int(get_jwt_identity())
    return jsonify([])


@bp.post("")
@jwt_required()
def register_trusted_device():
    uid = int(get_jwt_identity())
    return jsonify(id=0, trust_score=0, last_seen_at=None), 201


@bp.delete("/<int:device_id>")
@jwt_required()
def remove_trusted_device(device_id: int):
    uid = int(get_jwt_identity())
    return jsonify(message="removed"), 200
