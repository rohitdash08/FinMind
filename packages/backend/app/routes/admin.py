"""Admin routes — audit log viewer (Issue #76, GDPR).

Endpoints
---------
GET /api/admin/audit-log  — Paginated audit log (admin only).
"""
from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import AuditLog, Role, User

bp = Blueprint("admin", __name__)
logger = logging.getLogger("finmind.admin")


def _require_admin():
    """Return (user, error_response) tuple.

    If the caller is not an admin, *user* is None and *error_response* is a
    Flask response tuple ready to be returned.  Otherwise *error_response* is
    None.
    """
    uid = int(get_jwt_identity())
    user: User | None = db.session.get(User, uid)
    if user is None:
        return None, (jsonify(error="user not found"), 404)
    if user.role != Role.ADMIN.value:
        logger.warning("Admin access denied for user_id=%s role=%s", uid, user.role)
        return None, (jsonify(error="admin access required"), 403)
    return user, None


# ---------------------------------------------------------------------------
# GET /api/admin/audit-log
# ---------------------------------------------------------------------------

@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    """Return a paginated list of audit log entries.

    Query parameters
    ----------------
    user_id    : int    — Filter by user ID.
    action     : str    — Filter by action string (exact match).
    start_date : str    — ISO-8601 date, filter entries on/after this date.
    end_date   : str    — ISO-8601 date, filter entries on/before this date.
    page       : int    — 1-based page number (default: 1).
    page_size  : int    — Results per page (default: 50, max: 200).

    Returns
    -------
    200  — Paginated audit log.
    400  — Invalid query parameters.
    403  — Caller is not an admin.
    404  — User not found.
    """
    _user, err = _require_admin()
    if err:
        return err

    # --- parse pagination ---
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination parameters"), 400

    # --- parse filters ---
    filter_user_id = request.args.get("user_id")
    filter_action = request.args.get("action")
    filter_start = request.args.get("start_date")
    filter_end = request.args.get("end_date")

    try:
        filter_user_id = int(filter_user_id) if filter_user_id else None
        start_dt = datetime.fromisoformat(filter_start) if filter_start else None
        end_dt = datetime.fromisoformat(filter_end) if filter_end else None
    except (ValueError, TypeError):
        return jsonify(error="invalid filter parameters"), 400

    # --- build query ---
    query = db.session.query(AuditLog)

    if filter_user_id is not None:
        query = query.filter(AuditLog.user_id == filter_user_id)
    if filter_action:
        query = query.filter(AuditLog.action == filter_action)
    if start_dt:
        query = query.filter(AuditLog.created_at >= start_dt)
    if end_dt:
        query = query.filter(AuditLog.created_at <= end_dt)

    total = query.count()
    entries = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    logger.info(
        "Admin audit-log query page=%s page_size=%s total=%s", page, page_size, total
    )

    return jsonify(
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),  # ceiling division
        entries=[
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "details": e.details,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "created_at": e.created_at.isoformat() + "Z",
            }
            for e in entries
        ],
    ), 200
