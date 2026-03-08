"""GDPR endpoints: data export and account deletion."""

import io
import json
import zipfile
from datetime import datetime, date
from decimal import Decimal

from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db, redis_client
from ..models import (
    User, Category, Expense, RecurringExpense, Bill, Reminder,
    AdImpression, UserSubscription, AuditLog,
)
import logging

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


def _serialize(obj):
    """JSON serializer for non-standard types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _rows_to_dicts(rows, exclude=("password_hash",)):
    """Convert SQLAlchemy model instances to dicts."""
    result = []
    for row in rows:
        d = {}
        for col in row.__table__.columns:
            if col.name in exclude:
                continue
            val = getattr(row, col.name)
            d[col.name] = val
        result.append(d)
    return result


@bp.get("/export")
@jwt_required()
def export_data():
    """Export all user PII as a downloadable ZIP containing JSON files."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    data = {
        "user": _rows_to_dicts([user])[0],
        "categories": _rows_to_dicts(
            db.session.query(Category).filter_by(user_id=uid).all()
        ),
        "expenses": _rows_to_dicts(
            db.session.query(Expense).filter_by(user_id=uid).all()
        ),
        "recurring_expenses": _rows_to_dicts(
            db.session.query(RecurringExpense).filter_by(user_id=uid).all()
        ),
        "bills": _rows_to_dicts(
            db.session.query(Bill).filter_by(user_id=uid).all()
        ),
        "reminders": _rows_to_dicts(
            db.session.query(Reminder).filter_by(user_id=uid).all()
        ),
        "ad_impressions": _rows_to_dicts(
            db.session.query(AdImpression).filter_by(user_id=uid).all()
        ),
        "subscriptions": _rows_to_dicts(
            db.session.query(UserSubscription).filter_by(user_id=uid).all()
        ),
        "audit_logs": _rows_to_dicts(
            db.session.query(AuditLog).filter_by(user_id=uid).all()
        ),
        "exported_at": datetime.utcnow().isoformat(),
    }

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "finmind_export.json",
            json.dumps(data, indent=2, default=_serialize),
        )
    buf.seek(0)

    logger.info("Data export for user_id=%s", uid)

    # Audit
    db.session.add(AuditLog(user_id=uid, action="DATA_EXPORT"))
    db.session.commit()

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"finmind_export_{uid}.zip",
    )


@bp.delete("")
@jwt_required()
def delete_account():
    """Permanently delete user account and all associated data (GDPR right to erasure)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Delete all user data in dependency order
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(AdImpression).filter_by(user_id=uid).delete()
    db.session.query(UserSubscription).filter_by(user_id=uid).delete()
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()

    # Keep an anonymized audit log entry
    db.session.query(AuditLog).filter_by(user_id=uid).delete()
    db.session.add(AuditLog(user_id=None, action=f"ACCOUNT_DELETED:uid={uid}"))

    db.session.delete(user)
    db.session.commit()

    # Invalidate all Redis sessions for this user
    try:
        for key in redis_client.scan_iter(match="auth:refresh:*"):
            if redis_client.get(key) == str(uid).encode():
                redis_client.delete(key)
    except Exception:
        logger.warning("Failed to clear Redis sessions for user_id=%s", uid)

    logger.info("Account deleted for user_id=%s", uid)
    return jsonify(message="account permanently deleted"), 200
