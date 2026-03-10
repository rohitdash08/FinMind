from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash
from ..extensions import db
from ..models import (
    User,
    Category,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    UserSubscription,
    AuditLog,
)
import logging

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


def _serialize_date(val):
    if val is None:
        return None
    return val.isoformat()


def _serialize_decimal(val):
    if val is None:
        return None
    return float(val)


def _collect_user_data(user):
    """Gather all PII-linked records for a user into a structured dict."""
    categories = (
        db.session.query(Category).filter_by(user_id=user.id).all()
    )
    expenses = (
        db.session.query(Expense).filter_by(user_id=user.id).all()
    )
    recurring = (
        db.session.query(RecurringExpense).filter_by(user_id=user.id).all()
    )
    bills = db.session.query(Bill).filter_by(user_id=user.id).all()
    reminders = (
        db.session.query(Reminder).filter_by(user_id=user.id).all()
    )
    subscriptions = (
        db.session.query(UserSubscription).filter_by(user_id=user.id).all()
    )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": _serialize_date(user.created_at),
        },
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "created_at": _serialize_date(c.created_at),
            }
            for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "category_id": e.category_id,
                "amount": _serialize_decimal(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": _serialize_date(e.spent_at),
                "source_recurring_id": e.source_recurring_id,
                "created_at": _serialize_date(e.created_at),
            }
            for e in expenses
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "category_id": r.category_id,
                "amount": _serialize_decimal(r.amount),
                "currency": r.currency,
                "expense_type": r.expense_type,
                "notes": r.notes,
                "cadence": r.cadence.value if r.cadence else None,
                "start_date": _serialize_date(r.start_date),
                "end_date": _serialize_date(r.end_date),
                "active": r.active,
                "created_at": _serialize_date(r.created_at),
            }
            for r in recurring
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": _serialize_decimal(b.amount),
                "currency": b.currency,
                "next_due_date": _serialize_date(b.next_due_date),
                "cadence": b.cadence.value if b.cadence else None,
                "autopay_enabled": b.autopay_enabled,
                "active": b.active,
                "created_at": _serialize_date(b.created_at),
            }
            for b in bills
        ],
        "reminders": [
            {
                "id": rm.id,
                "bill_id": rm.bill_id,
                "message": rm.message,
                "send_at": _serialize_date(rm.send_at),
                "sent": rm.sent,
                "channel": rm.channel,
            }
            for rm in reminders
        ],
        "subscriptions": [
            {
                "id": s.id,
                "plan_id": s.plan_id,
                "active": s.active,
                "started_at": _serialize_date(s.started_at),
            }
            for s in subscriptions
        ],
    }


@bp.get("/export")
@jwt_required()
def export_pii():
    """Export all personal data for the authenticated user (GDPR Art. 20)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    data = _collect_user_data(user)

    audit = AuditLog(user_id=uid, action="PII_EXPORT")
    db.session.add(audit)
    db.session.commit()

    logger.info("PII export completed for user_id=%s", uid)
    return jsonify(data=data), 200


@bp.post("/delete")
@jwt_required()
def delete_account():
    """Permanently delete user account and all associated data (GDPR Art. 17).

    Requires password confirmation in the request body.
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    body = request.get_json() or {}
    password = body.get("password")
    if not password:
        return jsonify(error="password required for account deletion"), 400

    if not check_password_hash(user.password_hash, password):
        logger.warning("Delete account failed: wrong password user_id=%s", uid)
        return jsonify(error="invalid password"), 403

    # Log the deletion event before removing the user.
    # audit_logs.user_id uses ON DELETE SET NULL, so the log
    # row survives user deletion with user_id becoming NULL.
    audit = AuditLog(user_id=uid, action="ACCOUNT_DELETED")
    db.session.add(audit)
    db.session.flush()

    # Delete the user row. Cascading FKs handle related data:
    #   categories, expenses, recurring_expenses, bills,
    #   reminders, user_subscriptions -> ON DELETE CASCADE
    #   ad_impressions, audit_logs -> ON DELETE SET NULL
    db.session.delete(user)
    db.session.commit()

    logger.info("Account deleted for former user_id=%s", uid)
    return jsonify(message="account and all associated data deleted"), 200


@bp.get("/audit")
@jwt_required()
def audit_trail():
    """Retrieve audit log entries for the authenticated user."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    logs = (
        db.session.query(AuditLog)
        .filter_by(user_id=uid)
        .order_by(AuditLog.created_at.desc())
        .all()
    )

    return jsonify(
        audit_logs=[
            {
                "id": log.id,
                "action": log.action,
                "created_at": _serialize_date(log.created_at),
            }
            for log in logs
        ]
    ), 200
