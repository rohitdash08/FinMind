"""
PII Export & Delete routes — GDPR-ready endpoints.

Endpoints:
    GET  /pii/export   — Download a JSON export of all personal data
    POST /pii/delete   — Irreversibly delete all personal data (requires confirmation)
"""

import json
import logging
from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.pii import export_user_data, delete_user_data

bp = Blueprint("pii", __name__)
logger = logging.getLogger("finmind.pii")


@bp.get("/export")
@jwt_required()
def export_data():
    """
    Export all personal data as a downloadable JSON file.

    Returns a JSON package containing:
    - User profile (excluding password hash)
    - Categories, expenses, recurring expenses
    - Bills, reminders
    - Ad impressions, subscriptions
    - Audit logs

    Response: 200 with JSON attachment, or 404 if user not found.
    """
    user_id = get_jwt_identity()
    data = export_user_data(user_id)

    if data is None:
        return jsonify(error="User not found"), 404

    # Return as downloadable JSON file
    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    return Response(
        json_bytes,
        mimetype="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=finmind-export-user-{user_id}.json",
            "Content-Length": str(len(json_bytes)),
        },
    )


@bp.post("/delete")
@jwt_required()
def delete_data():
    """
    Irreversibly delete all personal data.

    Requires a JSON body with:
        {"confirm": true}

    This action cannot be undone. All user data including the account itself
    will be permanently removed. An anonymized audit trail entry is preserved
    for compliance purposes.

    Response: 200 with deletion summary, 400 if not confirmed, 404 if user not found.
    """
    user_id = get_jwt_identity()

    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return jsonify(
            error="Deletion requires explicit confirmation. Send {\"confirm\": true} to proceed."
        ), 400

    summary = delete_user_data(user_id)

    if summary is None:
        return jsonify(error="User not found"), 404

    logger.info("User %d data deletion completed", user_id)
    return jsonify(
        message="All personal data has been permanently deleted.",
        deleted=summary,
    ), 200
