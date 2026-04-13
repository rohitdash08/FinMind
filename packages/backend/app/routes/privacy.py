"""PII export & deletion endpoints (GDPR-ready)."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.privacy import delete_user_data, export_user_data, get_audit_log
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


@bp.get("/export")
@jwt_required()
def export_data():
    """Export all PII for the authenticated user as JSON + CSV."""
    uid = int(get_jwt_identity())
    try:
        result = export_user_data(uid)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    logger.info("PII export requested user=%s", uid)
    return jsonify(
        json_data=result["json_export"],
        csv_data=result["csv_export"],
        summary=result["summary"],
    )


@bp.post("/delete")
@jwt_required()
def delete_data():
    """Permanently delete all data for the authenticated user.

    Requires ``{"confirm": true}`` in the request body.
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("confirm"):
        return jsonify(error="confirmation required: send {\"confirm\": true}"), 400
    try:
        counts = delete_user_data(uid)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    logger.info("PII deletion completed user=%s counts=%s", uid, counts)
    return jsonify(message="all data permanently deleted", deleted=counts)


@bp.get("/audit-log")
@jwt_required()
def audit_log():
    """Return privacy-related audit log entries."""
    uid = int(get_jwt_identity())
    entries = get_audit_log(uid)
    return jsonify(entries)
