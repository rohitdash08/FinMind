"""
GDPR Routes
-----------
GET  /gdpr/export          - Download ZIP of all personal data
DELETE /gdpr/account       - Permanently delete account and all PII
GET  /gdpr/audit-log       - View GDPR action history for current user
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, make_response
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.gdpr import GDPRService

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


@bp.get("/export")
@jwt_required()
def export_data():
    """
    Stream a ZIP archive containing all personal data for the authenticated user.
    Compliant with GDPR Art. 20 (right to data portability).
    """
    user_id = int(get_jwt_identity())
    try:
        svc = GDPRService(user_id)
        zip_bytes = svc.export_zip()
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    except Exception:
        logger.exception("GDPR export failed for user_id=%s", user_id)
        return jsonify(error="Export failed. Please try again later."), 500

    response = make_response(zip_bytes)
    response.headers["Content-Type"] = "application/zip"
    response.headers["Content-Disposition"] = "attachment; filename=finmind_data_export.zip"
    response.headers["Content-Length"] = len(zip_bytes)
    return response


@bp.delete("/account")
@jwt_required()
def delete_account():
    """
    Permanently and irreversibly delete the authenticated user's account and
    all associated personal data. This action cannot be undone.
    Compliant with GDPR Art. 17 (right to erasure).
    """
    user_id = int(get_jwt_identity())
    try:
        svc = GDPRService(user_id)
        result = svc.delete_account()
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    except Exception:
        logger.exception("GDPR delete failed for user_id=%s", user_id)
        return jsonify(error="Deletion failed. Please try again later."), 500

    return jsonify(result), 200


@bp.get("/audit-log")
@jwt_required()
def audit_log():
    """
    Return the GDPR audit trail for the authenticated user.
    Lists all export and deletion events with timestamps.
    """
    from ..extensions import db
    from ..models import AuditLog

    user_id = int(get_jwt_identity())
    entries = (
        db.session.query(AuditLog)
        .filter_by(user_id=user_id)
        .order_by(AuditLog.performed_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        {
            "audit_log": [
                {
                    "id": e.id,
                    "action": e.action,
                    "detail": e.detail,
                    "performed_at": e.performed_at.isoformat(),
                }
                for e in entries
            ]
        }
    ), 200
