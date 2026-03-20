from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.secure_backup import create_encrypted_export, decrypt_data

bp = Blueprint("secure_backup", __name__)


@bp.route("/export-encrypted", methods=["POST"])
@jwt_required()
def export_encrypted():
    """
    POST /insights/export-encrypted

    Export user transactions as an encrypted backup file.
    The encrypted_data can be stored safely and decrypted with /insights/decrypt-export.

    Request body:
        password: str            — encryption password (required)
        months: int              — months of history to export (1-60, default 12)
        categories: list[str]    — optional category filter
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    password = data.get("password", "")
    if not password:
        return jsonify({"error": "password is required for encrypted export"}), 400

    months = int(data.get("months", 12))
    categories = data.get("categories")

    result = create_encrypted_export(
        user_id=int(user_id),
        password=password,
        months=months,
        include_categories=categories,
    )

    return jsonify(
        {
            "export_id": result.export.export_id,
            "encrypted_data": result.export.encrypted_data,
            "checksum": result.export.checksum,
            "record_count": result.export.record_count,
            "encryption_hint": result.export.encryption_hint,
            "created_at": result.export.created_at,
            "summary": result.summary,
        }
    )


@bp.route("/decrypt-export", methods=["POST"])
@jwt_required()
def decrypt_export():
    """
    POST /insights/decrypt-export

    Decrypt a previously exported backup.

    Request body:
        encrypted_data: str      — base64 ciphertext from export
        password: str            — decryption password
        expected_checksum: str   — (optional) SHA-256 checksum to verify integrity
    """
    data = request.get_json(silent=True) or {}
    encrypted_data = data.get("encrypted_data", "")
    password = data.get("password", "")
    expected_checksum = data.get("expected_checksum")

    if not encrypted_data or not password:
        return jsonify({"error": "encrypted_data and password are required"}), 400

    try:
        plaintext = decrypt_data(encrypted_data, password)
        import json
        import hashlib
        actual_checksum = hashlib.sha256(plaintext.encode('utf-8')).hexdigest()
        payload = json.loads(plaintext)

        integrity_ok = True
        if expected_checksum and expected_checksum != actual_checksum:
            integrity_ok = False

        return jsonify(
            {
                "decrypted": payload,
                "checksum": actual_checksum,
                "integrity_verified": integrity_ok,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Decryption failed: {str(e)}"}), 400