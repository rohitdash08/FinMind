"""
PII Export & Delete Routes (GDPR-ready)
Issue #76: https://github.com/rohitdash08/FinMind/issues/76

Endpoints:
  POST /privacy/export          - Request data export
  GET  /privacy/export/<id>     - Download export package
  POST /privacy/delete          - Request account deletion (returns token)
  POST /privacy/delete/confirm  - Confirm deletion with token (irreversible)
  GET  /privacy/requests        - List all data requests for current user
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.privacy import (
    request_export,
    get_export_package,
    request_deletion,
    confirm_deletion,
    get_request_history,
    PrivacyServiceError,
    RateLimitExceeded,
    TokenExpired,
    TokenInvalid,
)
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy.routes")


@bp.post("/export")
@jwt_required()
def create_export():
    """Request a full data export (GDPR Art. 20 - Data Portability)."""
    user_id = get_jwt_identity()
    try:
        dr = request_export(int(user_id))
        return jsonify(
            message="Export completed",
            request_id=dr.id,
            status=dr.status,
            download_url=f"/privacy/export/{dr.id}",
        ), 201
    except RateLimitExceeded as e:
        return jsonify(error=str(e)), 429
    except PrivacyServiceError as e:
        logger.error("Export failed for user_id=%s: %s", user_id, e)
        return jsonify(error="Export failed"), 500


@bp.get("/export/<int:request_id>")
@jwt_required()
def download_export(request_id):
    """Download a completed export package."""
    user_id = get_jwt_identity()
    package = get_export_package(request_id, int(user_id))
    if not package:
        return jsonify(error="Export not found or expired"), 404
    return jsonify(package), 200


@bp.post("/delete")
@jwt_required()
def create_deletion_request():
    """
    Request account deletion (GDPR Art. 17 - Right to Erasure).
    Returns a confirmation token valid for 30 minutes.
    """
    user_id = get_jwt_identity()
    try:
        dr = request_deletion(int(user_id))
        return jsonify(
            message="Deletion requested. Confirm within 30 minutes.",
            request_id=dr.id,
            confirmation_token=dr.confirmation_token,
            expires_at=dr.token_expires_at.isoformat(),
            confirm_url="/privacy/delete/confirm",
            warning="This action is IRREVERSIBLE. All data will be permanently deleted.",
        ), 200
    except PrivacyServiceError as e:
        logger.error("Deletion request failed for user_id=%s: %s", user_id, e)
        return jsonify(error="Deletion request failed"), 500


@bp.post("/delete/confirm")
@jwt_required()
def confirm_deletion_request():
    """
    Confirm and execute account deletion. IRREVERSIBLE.
    Requires the confirmation_token from /delete response.
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    token = data.get("confirmation_token")

    if not token:
        return jsonify(error="confirmation_token required"), 400

    try:
        dr = confirm_deletion(int(user_id), token)
        return jsonify(
            message="Account permanently deleted",
            status=dr.status,
            metadata=dr.metadata_json,
        ), 200
    except TokenInvalid as e:
        return jsonify(error=str(e)), 400
    except TokenExpired as e:
        return jsonify(error=str(e)), 410
    except PrivacyServiceError as e:
        logger.error("Deletion confirmation failed for user_id=%s: %s", user_id, e)
        return jsonify(error="Deletion failed"), 500


@bp.get("/requests")
@jwt_required()
def list_requests():
    """List all data export/deletion requests for the current user."""
    user_id = get_jwt_identity()
    history = get_request_history(int(user_id))
    return jsonify(requests=history), 200
