"""GDPR privacy endpoints: PII export and account deletion."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.privacy import delete_user_data, export_user_data
from ..services.cache import cache_delete_patterns

bp = Blueprint("privacy", __name__)


@bp.get("/export")
@jwt_required()
def pii_export():
    """Export all personal data for the authenticated user (GDPR Art. 20)."""
    uid = int(get_jwt_identity())
    data = export_user_data(uid)
    if not data:
        return jsonify(error="user not found"), 404
    return jsonify(data)


@bp.post("/delete")
@jwt_required()
def pii_delete():
    """Permanently delete all personal data (GDPR Art. 17 – Right to Erasure).

    Requires `{"confirm": true}` in the request body to prevent accidental
    deletion.
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return jsonify(error="send {\"confirm\": true} to confirm deletion"), 400

    success = delete_user_data(uid)
    if not success:
        return jsonify(error="user not found"), 404

    # Invalidate all cached data for this user
    cache_delete_patterns([f"user:{uid}:*"])

    return jsonify(message="All personal data has been permanently deleted."), 200
