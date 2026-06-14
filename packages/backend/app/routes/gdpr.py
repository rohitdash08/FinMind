"""
GDPR / Privacy routes

GET  /gdpr/export       → JSON export of all user PII
GET  /gdpr/export/csv   → CSV export of expenses
POST /gdpr/delete       → Initiate deletion (30-day grace period)
POST /gdpr/delete/confirm → Hard-delete (admin or after grace period; requires
                             re-authentication via password confirmation)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import AuditLog, User
from ..services.gdpr import (
    DELETION_GRACE_DAYS,
    GDPR_ACTION_DELETE_INITIATED,
    execute_deletion,
    export_user_data,
    export_user_data_csv,
    initiate_deletion,
)

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr.routes")


def _get_request_meta() -> tuple[str, str]:
    ip = (
        request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        .split(",")[0]
        .strip()
    )
    ua = request.headers.get("User-Agent", "unknown")[:200]
    return ip, ua


# ── Export ─────────────────────────────────────────────────────────────────────


@bp.get("/export")
@jwt_required()
def export_json():
    """
    Return a JSON file containing all PII for the authenticated user.

    Writes a GDPR_EXPORT audit record.
    """
    user_id = int(get_jwt_identity())
    ip, ua = _get_request_meta()

    try:
        payload = export_user_data(user_id, ip, ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404

    json_bytes = json.dumps(payload, indent=2, default=str).encode("utf-8")

    return Response(
        json_bytes,
        status=200,
        mimetype="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename=finmind-export-{user_id}.json"
            ),
            "Content-Length": str(len(json_bytes)),
        },
    )


@bp.get("/export/csv")
@jwt_required()
def export_csv():
    """
    Return a CSV file containing the authenticated user's expenses.

    Writes a GDPR_EXPORT audit record.
    """
    user_id = int(get_jwt_identity())
    ip, ua = _get_request_meta()

    try:
        csv_bytes = export_user_data_csv(user_id, ip, ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404

    return Response(
        csv_bytes,
        status=200,
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=finmind-expenses-{user_id}.csv"
            ),
            "Content-Length": str(len(csv_bytes)),
        },
    )


# ── Delete ─────────────────────────────────────────────────────────────────────


@bp.post("/delete")
@jwt_required()
def delete_initiate():
    """
    Initiate the GDPR deletion workflow.

    Writes a GDPR_DELETE_INITIATED audit record and returns the scheduled
    deletion date (now + 30-day grace period).

    The user account is NOT deleted immediately; they have 30 days to cancel
    by contacting support.
    """
    user_id = int(get_jwt_identity())
    ip, ua = _get_request_meta()

    # Require password re-confirmation as a safety gate.
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify(error="password required to confirm deletion request"), 400

    user: User | None = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="user not found"), 404

    if not check_password_hash(user.password_hash, password):
        logger.warning("GDPR delete initiation: wrong password for user_id=%s", user_id)
        return jsonify(error="invalid password"), 401

    # Check if a deletion has already been initiated.
    existing = (
        db.session.query(AuditLog)
        .filter(
            AuditLog.user_id == user_id,
            AuditLog.action.like(f"{GDPR_ACTION_DELETE_INITIATED}%"),
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if existing:
        scheduled_at = existing.created_at + timedelta(days=DELETION_GRACE_DAYS)
        if scheduled_at > datetime.utcnow():
            return (
                jsonify(
                    error="deletion already scheduled",
                    scheduled_deletion_at=scheduled_at.isoformat() + "Z",
                ),
                409,
            )

    try:
        result = initiate_deletion(user_id, ip, ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404

    return jsonify(result), 202


@bp.post("/delete/confirm")
@jwt_required()
def delete_confirm():
    """
    Execute the hard-delete after the grace period.

    Requires:
    - Valid JWT (user must still be able to log in)
    - password in body (re-authentication)
    - confirm=true in body (explicit opt-in)

    The grace period must have elapsed since the deletion was initiated, OR
    the request must come from an admin (role=ADMIN) acting on behalf of
    the user.

    GDPR audit log entries are preserved (user_id set to NULL).
    """
    user_id = int(get_jwt_identity())
    ip, ua = _get_request_meta()

    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    confirmed = data.get("confirm", False)

    if not password or not confirmed:
        return (
            jsonify(
                error="password and confirm=true required to permanently delete account"
            ),
            400,
        )

    user: User | None = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="user not found"), 404

    if not check_password_hash(user.password_hash, password):
        logger.warning("GDPR hard-delete: wrong password for user_id=%s", user_id)
        return jsonify(error="invalid password"), 401

    # Admins can force-delete immediately; regular users must wait for grace period.
    is_admin = getattr(user, "role", "") == "ADMIN"

    if not is_admin:
        initiated = (
            db.session.query(AuditLog)
            .filter(
                AuditLog.user_id == user_id,
                AuditLog.action.like(f"{GDPR_ACTION_DELETE_INITIATED}%"),
            )
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        if initiated is None:
            return (
                jsonify(
                    error="no deletion request found; call POST /gdpr/delete first"
                ),
                409,
            )

        scheduled_at = initiated.created_at + timedelta(days=DELETION_GRACE_DAYS)
        if datetime.utcnow() < scheduled_at:
            return (
                jsonify(
                    error="grace period has not elapsed yet",
                    scheduled_deletion_at=scheduled_at.isoformat() + "Z",
                    days_remaining=(scheduled_at - datetime.utcnow()).days,
                ),
                403,
            )

    try:
        result = execute_deletion(user_id, ip, ua)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404

    return jsonify(result), 200


# ── Audit trail (admin) ────────────────────────────────────────────────────────


@bp.get("/audit")
@jwt_required()
def audit_trail():
    """
    Return the GDPR audit trail for the authenticated user.
    Admins can pass ?user_id=<id> to view any user's trail.
    """
    requester_id = int(get_jwt_identity())
    requester: User | None = db.session.get(User, requester_id)
    if requester is None:
        return jsonify(error="user not found"), 404

    target_id = requester_id
    if requester.role == "ADMIN":
        qp = request.args.get("user_id")
        if qp:
            try:
                target_id = int(qp)
            except ValueError:
                return jsonify(error="invalid user_id"), 400

    logs = (
        db.session.query(AuditLog)
        .filter(
            AuditLog.user_id == target_id,
            AuditLog.action.like("GDPR_%"),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )

    return (
        jsonify(
            [
                {
                    "id": log.id,
                    "action": log.action,
                    "created_at": (
                        log.created_at.isoformat() if log.created_at else None
                    ),
                }
                for log in logs
            ]
        ),
        200,
    )
