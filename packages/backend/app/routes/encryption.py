from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.encryption import (
    setup_user_encryption,
    encrypt_field,
    decrypt_field,
    re_encrypt_dek,
    check_encryption_status,
)

encryption_bp = Blueprint("encryption", __name__, url_prefix="/encryption")


@encryption_bp.route("/setup", methods=["POST"])
@jwt_required()
def setup():
    """
    POST /encryption/setup
    Body: { password: string }
    Generates a fresh DEK, wraps under a KEK derived from password.
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    password = body.get("password")
    if not password:
        return jsonify({"error": "password required"}), 400
    try:
        result = setup_user_encryption(uid, password)
        return jsonify(result), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@encryption_bp.route("/status", methods=["GET"])
@jwt_required()
def status():
    """GET /encryption/status — Check if encryption is configured."""
    uid = int(get_jwt_identity())
    return jsonify(check_encryption_status(uid)), 200


@encryption_bp.route("/encrypt", methods=["POST"])
@jwt_required()
def encrypt():
    """
    POST /encryption/encrypt
    Body: { password: string, plaintext: string }
    Returns: { ciphertext: string (base64) }
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    password = body.get("password")
    plaintext = body.get("plaintext")
    if not password or plaintext is None:
        return jsonify({"error": "password and plaintext required"}), 400
    try:
        ct = encrypt_field(uid, password, str(plaintext))
        return jsonify({"ciphertext": ct}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@encryption_bp.route("/decrypt", methods=["POST"])
@jwt_required()
def decrypt():
    """
    POST /encryption/decrypt
    Body: { password: string, ciphertext: string (base64) }
    Returns: { plaintext: string }
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    password = body.get("password")
    ciphertext = body.get("ciphertext")
    if not password or not ciphertext:
        return jsonify({"error": "password and ciphertext required"}), 400
    try:
        pt = decrypt_field(uid, password, ciphertext)
        return jsonify({"plaintext": pt}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 401


@encryption_bp.route("/rotate", methods=["POST"])
@jwt_required()
def rotate():
    """
    POST /encryption/rotate
    Body: { old_password: string, new_password: string }
    Re-wraps the DEK under the new password (password change flow).
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    old_pw = body.get("old_password")
    new_pw = body.get("new_password")
    if not old_pw or not new_pw:
        return jsonify({"error": "old_password and new_password required"}), 400
    try:
        result = re_encrypt_dek(uid, old_pw, new_pw)
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
