"""User self-service routes — GDPR PII export & account deletion (Issue #76).

Endpoints
---------
GET  /api/user/export     — Download a JSON package of all personal data.
DELETE /api/user/account  — Permanently and irreversibly delete the account.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User
from ..services.audit import log_audit_event
from ..services.pii_service import build_export_package, delete_user_permanently

bp = Blueprint("user", __name__)
logger = logging.getLogger("finmind.user")


def _client_ip() -> str | None:
    """Return the best-guess client IP, respecting X-Forwarded-For."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


# ---------------------------------------------------------------------------
# GET /api/user/export
# ---------------------------------------------------------------------------

@bp.get("/export")
@jwt_required()
def export_user_data():
    """Export all personal data for the authenticated user as JSON.

    Returns
    -------
    200  — JSON package with all user data.
    404  — User not found (edge-case: account already deleted).
    500  — Unexpected server error.
    """
    uid = int(get_jwt_identity())
    logger.info("PII export requested user_id=%s", uid)

    user: User | None = db.session.get(User, uid)
    if user is None:
        return jsonify(error="user not found"), 404

    try:
        package = build_export_package(uid)
    except Exception as exc:
        logger.exception("PII export failed user_id=%s", uid)
        return jsonify(error="export failed", detail=str(exc)), 500

    # Audit trail — record *after* we know export succeeded
    log_audit_event(
        user_id=uid,
        action="pii_export",
        details={
            "email": user.email,
            "record_counts": {
                k: len(v) if isinstance(v, list) else 1
                for k, v in package.items()
                if k not in ("export_generated_at",)
            },
        },
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
    )

    logger.info("PII export completed user_id=%s", uid)
    return jsonify(package), 200


# ---------------------------------------------------------------------------
# DELETE /api/user/account
# ---------------------------------------------------------------------------

@bp.delete("/account")
@jwt_required()
def delete_account():
    """Permanently delete the authenticated user's account and all associated data.

    This action is **irreversible**.  A confirmation field is required in the
    request body to prevent accidental deletion.

    Request body (JSON)
    -------------------
    confirm : str  — Must equal ``"DELETE_MY_ACCOUNT"`` (case-sensitive).
    reason  : str  — Optional reason for deletion (stored in audit log).

    Returns
    -------
    200  — Account and all data deleted successfully.
    400  — Missing or incorrect confirmation string.
    404  — User not found.
    500  — Unexpected server error.
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    # Require explicit confirmation to prevent accidental deletion
    if data.get("confirm") != "DELETE_MY_ACCOUNT":
        return jsonify(
            error="confirmation required",
            detail="Send JSON body with \"confirm\": \"DELETE_MY_ACCOUNT\"",
        ), 400

    user: User | None = db.session.get(User, uid)
    if user is None:
        return jsonify(error="user not found"), 404

    user_email = user.email  # capture before deletion
    reason = str(data.get("reason") or "").strip() or None

    logger.warning(
        "Account deletion initiated user_id=%s email=%s", uid, user_email
    )

    # Write audit log *before* deletion (user row is about to be gone)
    log_audit_event(
        user_id=uid,
        action="account_deletion_initiated",
        details={"email": user_email, "reason": reason},
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
    )

    try:
        deleted_counts = delete_user_permanently(uid)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    except Exception:
        logger.exception("Account deletion failed user_id=%s", uid)
        return jsonify(error="deletion failed"), 500

    # Write a final tombstone audit entry (user_id is now NULL'd)
    log_audit_event(
        user_id=None,
        action="account_deletion_completed",
        details={
            "former_email": user_email,
            "reason": reason,
            "deleted_counts": deleted_counts,
        },
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
    )

    logger.warning(
        "Account deletion completed former_email=%s counts=%s",
        user_email,
        deleted_counts,
    )

    return jsonify(
        message="account and all associated data permanently deleted",
        deleted_counts=deleted_counts,
    ), 200
