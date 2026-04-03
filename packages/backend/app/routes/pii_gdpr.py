"""Routes for PII export & GDPR account deletion (issue #76)."""
from flask import Blueprint, request, jsonify, send_file
import io
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.pii_gdpr import export_user_pii, delete_user_pii

bp = Blueprint("pii_gdpr", __name__)


@bp.route("/account/export", methods=["GET"])
@jwt_required()
def export_pii():
    """Export all user personal data as JSON summary or ZIP download."""
    user_id = int(get_jwt_identity())
    fmt = request.args.get("format", "json").lower()

    package = export_user_pii(user_id)
    if not package:
        return jsonify({"error": "User not found"}), 404

    if fmt == "zip":
        zip_bytes = package.to_zip_bytes()
        return send_file(
            io.BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"finmind-export-{user_id}.zip",
        )

    # Default: JSON summary
    result = package.to_dict()
    result["checksum"] = package.checksum()
    return jsonify(result), 200


@bp.route("/account/delete", methods=["DELETE"])
@jwt_required()
def delete_account():
    """
    Permanently delete the user's account and all associated data.
    This is irreversible. A GDPR-compliant audit log entry is created.
    """
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    # Require explicit confirmation
    if data.get("confirm") != "DELETE_MY_ACCOUNT":
        return jsonify({
            "error": "Please confirm by setting confirm='DELETE_MY_ACCOUNT'",
            "irreversible": True,
        }), 400

    reason = data.get("reason", "user_requested")
    result = delete_user_pii(user_id=user_id, reason=reason)
    if not result:
        return jsonify({"error": "User not found"}), 404

    return jsonify(result), 200


@bp.route("/account/export/preview", methods=["GET"])
@jwt_required()
def preview_pii():
    """Preview what data would be exported (record counts only, no PII)."""
    user_id = int(get_jwt_identity())
    package = export_user_pii(user_id)
    if not package:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "user_id": user_id,
        "export_preview": {k: len(v) for k, v in package.sections.items()},
        "total_records": sum(len(v) for v in package.sections.values()),
        "note": "Use GET /account/export to download full data package",
    }), 200