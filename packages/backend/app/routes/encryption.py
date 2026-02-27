"""Client-side encryption API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.encryption import (
    setup_encryption, verify_passphrase, encrypt_field, decrypt_field,
    list_fields, delete_field, rotate_key, has_encryption,
)

bp = Blueprint("encryption", __name__)


@bp.get("/status")
@jwt_required()
def status():
    uid = int(get_jwt_identity())
    return jsonify({"enabled": has_encryption(uid)})


@bp.post("/setup")
@jwt_required()
def setup():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("passphrase"):
        return jsonify({"error": "passphrase required"}), 400
    try:
        return jsonify(setup_encryption(uid, data["passphrase"])), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/verify")
@jwt_required()
def verify():
    uid = int(get_jwt_identity())
    data = request.get_json() or 
    valid = verify_passphrase(uid, data.get("passphrase", ""))
    return jsonify({"valid": valid})


@bp.post("/encrypt")
@jwt_required()
def encrypt():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        result = encrypt_field(uid, data["passphrase"], data["field_name"], data["value"])
        return jsonify(result)
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/decrypt")
@jwt_required()
def decrypt():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        value = decrypt_field(uid, data["passphrase"], data["field_name"])
        return jsonify({"field_name": data["field_name"], "value": value})
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/fields")
@jwt_required()
def fields():
    uid = int(get_jwt_identity())
    return jsonify(list_fields(uid))


@bp.delete("/fields/<field_name>")
@jwt_required()
def remove(field_name):
    uid = int(get_jwt_identity())
    if delete_field(uid, field_name):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Field not found"}), 404


@bp.post("/rotate")
@jwt_required()
def rotate():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        result = rotate_key(uid, data["old_passphrase"], data["new_passphrase"])
        return jsonify(result)
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
