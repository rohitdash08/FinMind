"""GDPR privacy endpoints.

Provides user-facing and admin-facing routes for:
- Exporting all personal data (GET  /gdpr/export)
- Requesting account deletion  (POST /gdpr/delete)
- Cancelling a pending deletion (POST /gdpr/delete/cancel)
- Confirming immediate deletion (POST /gdpr/delete/confirm)
- Anonymizing account data      (POST /gdpr/anonymize)
- Viewing GDPR audit logs       (GET  /gdpr/audit-logs)  [admin]
- Checking deletion status      (GET  /gdpr/delete/status)
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import User, Role
from ..services import gdpr as gdpr_service

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


def _request_meta():
    """Extract IP and User-Agent from the current request."""
    return (
        request.remote_addr,
        request.headers.get("User-Agent", "")[:500],
    )


# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------


@bp.get("/export")
@jwt_required()
def export_data():
    """Download a JSON package containing all personal data."""
    uid = int(get_jwt_identity())
    ip, ua = _request_meta()
    try:
        package = gdpr_service.export_user_data(uid, ip=ip, ua=ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(package), 200


@bp.post("/delete")
@jwt_required()
def request_deletion():
    """Initiate an account deletion request (30-day grace period)."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    # Require password re-confirmation for safety
    password = data.get("password")
    if not password:
        return jsonify(error="password required for deletion request"), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    if not check_password_hash(user.password_hash, password):
        return jsonify(error="invalid password"), 403

    ip, ua = _request_meta()
    result = gdpr_service.request_deletion(
        uid, reason=data.get("reason"), ip=ip, ua=ua
    )
    status_code = 200 if result["status"] == "already_pending" else 202
    return jsonify(result), status_code


@bp.post("/delete/cancel")
@jwt_required()
def cancel_deletion():
    """Cancel a pending deletion request during the grace period."""
    uid = int(get_jwt_identity())
    ip, ua = _request_meta()
    result = gdpr_service.cancel_deletion(uid, ip=ip, ua=ua)
    code = 200 if result["status"] == "cancelled" else 404
    return jsonify(result), code


@bp.post("/delete/confirm")
@jwt_required()
def confirm_deletion():
    """Immediately and irreversibly delete the account (no grace period)."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    # Double-confirm with password
    password = data.get("password")
    if not password:
        return jsonify(error="password required for deletion confirmation"), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    if not check_password_hash(user.password_hash, password):
        return jsonify(error="invalid password"), 403

    ip, ua = _request_meta()
    try:
        result = gdpr_service.confirm_deletion(uid, ip=ip, ua=ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(result), 200


@bp.get("/delete/status")
@jwt_required()
def deletion_status():
    """Check whether a deletion request is pending."""
    uid = int(get_jwt_identity())
    from ..models import DeletionRequest

    req = (
        db.session.query(DeletionRequest)
        .filter_by(user_id=uid, cancelled=False, confirmed=False)
        .first()
    )
    if not req:
        return jsonify({"pending": False}), 200
    return jsonify({
        "pending": True,
        "scheduled_at": req.scheduled_at.isoformat() + "Z",
        "requested_at": req.requested_at.isoformat() + "Z",
    }), 200


@bp.post("/anonymize")
@jwt_required()
def anonymize():
    """Anonymize personal data while keeping financial records."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    password = data.get("password")
    if not password:
        return jsonify(error="password required for anonymization"), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    if not check_password_hash(user.password_hash, password):
        return jsonify(error="invalid password"), 403

    ip, ua = _request_meta()
    try:
        result = gdpr_service.anonymize_user(uid, ip=ip, ua=ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@bp.get("/audit-logs")
@jwt_required()
def list_audit_logs():
    """List GDPR audit log entries (admin-only)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != Role.ADMIN.value:
        return jsonify(error="admin access required"), 403

    target_user = request.args.get("user_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = min(100, request.args.get("page_size", 50, type=int))

    logs = gdpr_service.get_gdpr_audit_logs(user_id=target_user, page=page, page_size=page_size)
    return jsonify(logs), 200
