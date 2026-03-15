"""Routes for secure backup and encrypted export."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.backup import (
    create_backup,
    verify_backup,
    restore_preview,
    get_backup_history,
    delete_backup_record,
)

bp = Blueprint("backup", __name__)


@bp.route("/create", methods=["POST"])
@jwt_required()
def create_backup_endpoint():
    """Create a secure backup of user data.

    JSON body:
    - backup_type: 'full' | 'selective' (default 'full')
    - format: 'json' | 'csv' (default 'json')
    - encrypt: boolean (default true)
    - sections: list of sections for selective backup
    - passphrase: optional encryption passphrase
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    backup_type = data.get("backup_type", "full")
    fmt = data.get("format", "json")
    encrypt = data.get("encrypt", True)
    sections = data.get("sections")
    passphrase = data.get("passphrase")

    result = create_backup(
        user_id=user_id,
        backup_type=backup_type,
        format=fmt,
        encrypt=encrypt,
        sections=sections,
        passphrase=passphrase,
    )

    return jsonify(result), 201


@bp.route("/verify", methods=["POST"])
@jwt_required()
def verify_backup_endpoint():
    """Verify backup integrity.

    JSON body:
    - data: backup data
    - file_hash: expected SHA-256 hash
    """
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}

    backup_data = body.get("data")
    file_hash = body.get("file_hash")

    if not backup_data or not file_hash:
        return jsonify({"error": "data and file_hash are required"}), 400

    result = verify_backup(backup_data, file_hash)
    return jsonify(result), 200


@bp.route("/restore/preview", methods=["POST"])
@jwt_required()
def restore_preview_endpoint():
    """Preview what would be restored from a backup.

    JSON body:
    - data: backup data
    - encryption_key: base64 key (if encrypted)
    - passphrase: passphrase (if encrypted with passphrase)
    """
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}

    backup_data = body.get("data")
    if not backup_data:
        return jsonify({"error": "data is required"}), 400

    encryption_key = body.get("encryption_key")
    passphrase = body.get("passphrase")

    result = restore_preview(user_id, backup_data, encryption_key, passphrase)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result), 200


@bp.route("/history", methods=["GET"])
@jwt_required()
def backup_history():
    """Get backup history for the current user."""
    user_id = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)

    records = get_backup_history(user_id, limit)
    return jsonify({"backups": records, "count": len(records)}), 200


@bp.route("/<int:backup_id>", methods=["DELETE"])
@jwt_required()
def delete_backup(backup_id):
    """Delete a backup record."""
    user_id = int(get_jwt_identity())

    if delete_backup_record(user_id, backup_id):
        return jsonify({"message": "Backup deleted"}), 200

    return jsonify({"error": "Backup not found"}), 404
