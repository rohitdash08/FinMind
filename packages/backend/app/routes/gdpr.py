"""GDPR PII export & deletion REST endpoints.

Endpoints
---------
POST /gdpr/export          – Generate PII export package (JSON)
POST /gdpr/delete           – Request account deletion
POST /gdpr/delete/confirm   – Confirm deletion via token
POST /gdpr/delete/cancel    – Cancel pending deletion
GET  /gdpr/delete/status    – Check deletion request status
GET  /gdpr/audit            – Admin: view GDPR audit trail
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..extensions import db
from ..models import User, GDPRAuditLog, GDPRAction, Role
from ..services.gdpr import (
    export_user_pii,
    log_gdpr_event,
    request_deletion,
    confirm_deletion,
    cancel_deletion,
    execute_deletion,
    get_deletion_status,
)

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


# ---------------------------------------------------------------------------
# PII Export
# ---------------------------------------------------------------------------

@bp.post("/export")
@jwt_required()
def pii_export():
    """Generate and return a JSON package containing all PII for the
    authenticated user."""
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if user is None or user.is_deleted:
        return jsonify(error="user not found"), 404

    log_gdpr_event(user_id, user.email, GDPRAction.EXPORT_REQUESTED)
    package = export_user_pii(user_id)
    if package is None:
        return jsonify(error="export failed"), 500

    return jsonify(export=package), 200


# ---------------------------------------------------------------------------
# Deletion workflow
# ---------------------------------------------------------------------------

@bp.post("/delete")
@jwt_required()
def delete_request():
    """Request account deletion (starts grace period)."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    reason = data.get("reason")

    req, err = request_deletion(user_id, reason)
    if err:
        return jsonify(error=err), 400

    return jsonify(
        message="deletion requested",
        request_id=req.id,
        confirmation_token=req.confirmation_token,
        grace_period_ends_at=req.grace_period_ends_at.isoformat(),
    ), 201


@bp.post("/delete/confirm")
@jwt_required()
def delete_confirm():
    """Confirm deletion using the token received in the request step."""
    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")
    if not token:
        return jsonify(error="confirmation_token required"), 400

    req, err = confirm_deletion(token)
    if err:
        return jsonify(error=err), 400

    return jsonify(
        message="deletion confirmed – account will be permanently removed "
                f"after the grace period ends at {req.grace_period_ends_at.isoformat()}",
        request_id=req.id,
    ), 200


@bp.post("/delete/cancel")
@jwt_required()
def delete_cancel():
    """Cancel any pending or confirmed deletion."""
    user_id = int(get_jwt_identity())
    ok, err = cancel_deletion(user_id)
    if not ok:
        return jsonify(error=err), 400
    return jsonify(message="deletion cancelled"), 200


@bp.get("/delete/status")
@jwt_required()
def delete_status():
    """Return the latest deletion request status for the authenticated user."""
    user_id = int(get_jwt_identity())
    req = get_deletion_status(user_id)
    if req is None:
        return jsonify(deletion_request=None), 200
    return jsonify(deletion_request={
        "id": req.id,
        "status": req.status,
        "reason": req.reason,
        "grace_period_ends_at": req.grace_period_ends_at.isoformat(),
        "confirmed_at": req.confirmed_at.isoformat() if req.confirmed_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "created_at": req.created_at.isoformat(),
    }), 200


# ---------------------------------------------------------------------------
# Admin: execute deletion & audit trail
# ---------------------------------------------------------------------------

@bp.post("/delete/execute/<int:target_user_id>")
@jwt_required()
def delete_execute(target_user_id):
    """Admin-only: execute a confirmed deletion whose grace period has
    elapsed."""
    caller_id = int(get_jwt_identity())
    caller = db.session.get(User, caller_id)
    if caller is None or caller.role != Role.ADMIN.value:
        return jsonify(error="admin access required"), 403

    ok, err = execute_deletion(target_user_id)
    if not ok:
        return jsonify(error=err), 400
    return jsonify(message="user data permanently deleted"), 200


@bp.get("/audit")
@jwt_required()
def audit_trail():
    """Admin-only: paginated GDPR audit log."""
    caller_id = int(get_jwt_identity())
    caller = db.session.get(User, caller_id)
    if caller is None or caller.role != Role.ADMIN.value:
        return jsonify(error="admin access required"), 403

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    user_filter = request.args.get("user_id", type=int)

    query = GDPRAuditLog.query.order_by(GDPRAuditLog.created_at.desc())
    if user_filter:
        query = query.filter_by(user_id=user_filter)

    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        audit_logs=[
            {
                "id": log.id,
                "user_id": log.user_id,
                "user_email": log.user_email,
                "action": log.action,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        total=total,
        page=page,
        per_page=per_page,
    ), 200
