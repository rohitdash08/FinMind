"""Client-Side Encryption API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.client_encryption import (
    EncryptionMetadata, KeyManager, FieldEncryptor,
    generate_client_encryption_config,
)

bp = Blueprint("client_encryption", __name__)


@bp.post("/config")
@jwt_required()
def get_encryption_config():
    """Get client-side encryption configuration."""
    user_id = get_jwt_identity()
    config = generate_client_encryption_config(str(user_id))
    return jsonify(config)


@bp.post("/rotate-key")
@jwt_required()
def rotate_key():
    """Rotate encryption key."""
    user_id = str(get_jwt_identity())
    km = KeyManager(user_id)
    new_key = km.rotate_key()
    return jsonify({"status": "rotated", "new_version": new_key["version"], "key": new_key})


@bp.post("/validate")
@jwt_required()
def validate_encrypted_data():
    """Validate that data fields are properly encrypted."""
    data = request.get_json() or {}
    record = data.get("record", {})
    sensitive_fields = data.get("sensitive_fields", None)

    result = FieldEncryptor.validate_encrypted_record(record, sensitive_fields)
    return jsonify(result)


@bp.post("/key-history")
@jwt_required()
def key_history():
    """Get encryption key version history."""
    user_id = str(get_jwt_identity())
    km = KeyManager(user_id)
    return jsonify({"key_versions": km.get_key_history()})
