from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.client_encryption import (
    encrypt_field,
    decrypt_field,
    generate_user_key_material,
    test_encryption_roundtrip,
)

bp = Blueprint("client_encryption", __name__)


@bp.route("/encryption/keygen", methods=["POST"])
@jwt_required()
def keygen():
    """
    POST /insights/encryption/keygen
    Generate key material (salt + key_id) for a user.
    The actual encryption key is derived from user password + salt client-side.
    """
    user_id = get_jwt_identity()
    material = generate_user_key_material(user_id)
    return jsonify(material)


@bp.route("/encryption/encrypt", methods=["POST"])
@jwt_required()
def encrypt():
    """
    POST /insights/encryption/encrypt
    Body: { "plaintext": "...", "password": "..." }
    Returns encrypted blob. For proxy/test use.
    """
    body = request.get_json(silent=True) or {}
    plaintext = body.get("plaintext", "")
    password = body.get("password", "")
    if not plaintext or not password:
        return jsonify({"error": "plaintext and password are required"}), 400

    encrypted = encrypt_field(plaintext, password)
    return jsonify({"encrypted": encrypted})


@bp.route("/encryption/decrypt", methods=["POST"])
@jwt_required()
def decrypt():
    """
    POST /insights/encryption/decrypt
    Body: { "encrypted": "...", "password": "..." }
    Returns decrypted plaintext if auth tag is valid.
    """
    body = request.get_json(silent=True) or {}
    encrypted = body.get("encrypted", "")
    password = body.get("password", "")
    if not encrypted or not password:
        return jsonify({"error": "encrypted and password are required"}), 400

    try:
        plaintext = decrypt_field(encrypted, password)
        return jsonify({"plaintext": plaintext})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/encryption/test", methods=["GET"])
@jwt_required()
def encryption_test():
    """
    GET /insights/encryption/test
    Run a self-test of the encryption system with a random ephemeral value.
    """
    import os
    test_value = f"test-{os.urandom(8).hex()}"
    test_password = os.urandom(16).hex()
    result = test_encryption_roundtrip(test_value, test_password)
    return jsonify({
        "success": result.success,
        "original_length": result.original_length,
        "encrypted_length": result.encrypted_length,
        "error": result.error,
    })