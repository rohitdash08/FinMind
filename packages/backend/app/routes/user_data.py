"""GDPR-compliant PII export and account deletion endpoints."""

import io
import json
import logging
import zipfile
from datetime import datetime

from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    AdImpression,
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
    User,
    UserSubscription,
)

bp = Blueprint("user_data", __name__)
logger = logging.getLogger("finmind.user_data")


def _collect_user_data(user_id: int) -> dict:
    """Collect all PII data for a user into a structured dict."""
    user = db.session.get(User, user_id)
    if not user:
        return {}

    categories = Category.query.filter_by(user_id=user_id).all()
    expenses = Expense.query.filter_by(user_id=user_id).all()
    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    bills = Bill.query.filter_by(user_id=user_id).all()
    reminders = Reminder.query.filter_by(user_id=user_id).all()
    subscriptions = UserSubscription.query.filter_by(user_id=user_id).all()
    ad_impressions = AdImpression.query.filter_by(user_id=user_id).all()
    audit_logs = AuditLog.query.filter_by(user_id=user_id).all()

    return {
        "export_metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "format_version": "1.0",
        },
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "category_id": e.category_id,
                "amount": float(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in expenses
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "category_id": r.category_id,
                "amount": float(r.amount),
                "currency": r.currency,
                "expense_type": r.expense_type,
                "notes": r.notes,
                "cadence": r.cadence.value if r.cadence else None,
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "active": r.active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recurring
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
                "cadence": b.cadence.value if b.cadence else None,
                "autopay_enabled": b.autopay_enabled,
                "active": b.active,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bills
        ],
        "reminders": [
            {
                "id": r.id,
                "bill_id": r.bill_id,
                "message": r.message,
                "send_at": r.send_at.isoformat() if r.send_at else None,
                "sent": r.sent,
                "channel": r.channel,
            }
            for r in reminders
        ],
        "subscriptions": [
            {
                "id": s.id,
                "plan_id": s.plan_id,
                "active": s.active,
                "started_at": s.started_at.isoformat() if s.started_at else None,
            }
            for s in subscriptions
        ],
        "audit_logs": [
            {
                "id": a.id,
                "action": a.action,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audit_logs
        ],
    }


@bp.get("/export")
@jwt_required()
def export_user_data():
    """Export all user data as a downloadable ZIP file (GDPR Art. 20)."""
    user_id = get_jwt_identity()

    log = AuditLog(user_id=user_id, action="DATA_EXPORT_REQUESTED")
    db.session.add(log)
    db.session.commit()

    logger.info("Data export requested by user %s", user_id)

    data = _collect_user_data(user_id)
    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("finmind-export/user_data.json", json_bytes)
        zf.writestr(
            "finmind-export/README.txt",
            "This archive contains all personal data associated with your FinMind account.\n"
            "Generated per GDPR Article 20 - Right to Data Portability.\n",
        )
    buf.seek(0)

    log_completed = AuditLog(user_id=user_id, action="DATA_EXPORT_COMPLETED")
    db.session.add(log_completed)
    db.session.commit()

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"finmind-export-{user_id}-{datetime.utcnow().strftime('%Y%m%d')}.zip",
    )


@bp.delete("/delete")
@jwt_required()
def delete_user_data():
    """Permanently delete all user data (GDPR Art. 17 - Right to Erasure).

    This is irreversible. All expenses, categories, bills, reminders,
    subscriptions, and the user account itself will be deleted.
    """
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error="User not found"), 404

    log = AuditLog(user_id=user_id, action="DATA_DELETION_REQUESTED")
    db.session.add(log)
    db.session.commit()

    logger.warning("Data deletion requested by user %s (%s)", user_id, user.email)

    try:
        # Delete in correct order (respecting foreign keys)
        AuditLog.query.filter_by(user_id=user_id).delete()
        Reminder.query.filter_by(user_id=user_id).delete()
        UserSubscription.query.filter_by(user_id=user_id).delete()
        AdImpression.query.filter_by(user_id=user_id).delete()
        Expense.query.filter_by(user_id=user_id).delete()
        RecurringExpense.query.filter_by(user_id=user_id).delete()
        Bill.query.filter_by(user_id=user_id).delete()
        Category.query.filter_by(user_id=user_id).delete()

        # Delete the user account itself
        db.session.delete(user)
        db.session.commit()

        logger.warning("User %s and all associated data permanently deleted", user_id)

        return jsonify(
            message="All data has been permanently deleted.",
            deleted_at=datetime.utcnow().isoformat(),
        ), 200

    except Exception as e:
        db.session.rollback()
        logger.error("Failed to delete user %s data: %s", user_id, e)
        return jsonify(error="Deletion failed. Please contact support."), 500


@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    """View audit log of GDPR-related actions on this account."""
    user_id = get_jwt_identity()
    logs = (
        AuditLog.query.filter_by(user_id=user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(
        entries=[
            {
                "id": entry.id,
                "action": entry.action,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in logs
        ]
    )
