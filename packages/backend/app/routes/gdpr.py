"""GDPR-compliant PII export and deletion routes.

Endpoints:
  GET  /gdpr/users/<id>/export  – download all personal data as JSON
  DELETE /gdpr/users/<id>       – irreversibly delete user and all data
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, AuditLog
from ..services.gdpr import collect_user_data, permanently_delete_user, log_audit_action

bp = Blueprint("gdpr", __name__)


@bp.get("/users/<int:user_id>/export")
@jwt_required()
def export_user_data(user_id: int):
    """Export all PII for the authenticated user as a JSON package."""
    current_uid = int(get_jwt_identity())
    if current_uid != user_id:
        return jsonify(error="forbidden – can only export your own data"), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error="user not found"), 404

    ip_address = request.remote_addr
    data = collect_user_data(user_id)

    # Audit trail
    log_audit_action(
        user_id=user_id,
        action="GDPR_DATA_EXPORT",
        ip_address=ip_address,
    )

    return jsonify(data), 200


@bp.delete("/users/<int:user_id>")
@jwt_required()
def delete_user(user_id: int):
    """Irreversibly delete the authenticated user and all associated data.

    Requires a JSON body with ``{"confirm": true}`` to prevent accidental
    deletion.
    """
    current_uid = int(get_jwt_identity())
    if current_uid != user_id:
        return jsonify(error="forbidden – can only delete your own data"), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error="user not found"), 404

    # Require explicit confirmation
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify(error="confirmation required – send {\"confirm\": true}"), 400

    ip_address = request.remote_addr

    # Audit trail – log *before* deletion so user_id FK is still valid
    log_audit_action(
        user_id=user_id,
        action="GDPR_DATA_DELETE",
        ip_address=ip_address,
    )

    # Set user_id on audit logs to NULL before deleting the user,
    # so the audit record survives (GDPR requires we keep evidence of deletion).
    db.session.query(AuditLog).filter_by(user_id=user_id).update(
        {"user_id": None}, synchronize_session="fetch"
    )
    db.session.commit()

    success = permanently_delete_user(user_id)
    if not success:
        return jsonify(error="deletion failed"), 500

    return jsonify(message="user and all associated data permanently deleted"), 200
