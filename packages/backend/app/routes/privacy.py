from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    User, Category, Expense, RecurringExpense,
    Bill, Reminder, AdImpression, UserSubscription, AuditLog
)
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")

@bp.get("/export")
@jwt_required()
def export_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Extract all data for the user
    categories = db.session.query(Category).filter_by(user_id=uid).all()
    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    recurring = db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    bills = db.session.query(Bill).filter_by(user_id=uid).all()
    reminders = db.session.query(Reminder).filter_by(user_id=uid).all()
    subscriptions = db.session.query(UserSubscription).filter_by(user_id=uid).all()
    audit_logs = db.session.query(AuditLog).filter_by(user_id=uid).all()

    data = {
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None
        },
        "categories": [{"id": c.id, "name": c.name, "created_at": c.created_at.isoformat() if c.created_at else None} for c in categories],
        "expenses": [{
            "id": e.id, "category_id": e.category_id, "amount": float(e.amount),
            "currency": e.currency, "expense_type": e.expense_type, "notes": e.notes,
            "spent_at": e.spent_at.isoformat() if e.spent_at else None,
            "source_recurring_id": e.source_recurring_id,
            "created_at": e.created_at.isoformat() if e.created_at else None
        } for e in expenses],
        "recurring_expenses": [{
            "id": r.id, "category_id": r.category_id, "amount": float(r.amount),
            "currency": r.currency, "expense_type": r.expense_type, "notes": r.notes,
            "cadence": r.cadence, "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "active": r.active, "created_at": r.created_at.isoformat() if r.created_at else None
        } for r in recurring],
        "bills": [{
            "id": b.id, "name": b.name, "amount": float(b.amount),
            "currency": b.currency, "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
            "cadence": b.cadence, "autopay_enabled": b.autopay_enabled,
            "channel_whatsapp": b.channel_whatsapp, "channel_email": b.channel_email,
            "active": b.active, "created_at": b.created_at.isoformat() if b.created_at else None
        } for b in bills],
        "reminders": [{
            "id": r.id, "bill_id": r.bill_id, "message": r.message,
            "send_at": r.send_at.isoformat() if r.send_at else None,
            "sent": r.sent, "channel": r.channel
        } for r in reminders],
        "subscriptions": [{
            "id": s.id, "plan_id": s.plan_id, "active": s.active,
            "started_at": s.started_at.isoformat() if s.started_at else None
        } for s in subscriptions],
        "audit_logs": [{
            "id": a.id, "action": a.action, "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in audit_logs]
    }

    logger.info("Exported PII for user_id=%s", uid)
    return jsonify(data), 200


@bp.delete("/delete")
@jwt_required()
def delete_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Delete related data first
    db.session.query(AuditLog).filter_by(user_id=uid).delete()
    db.session.query(UserSubscription).filter_by(user_id=uid).delete()
    db.session.query(AdImpression).filter_by(user_id=uid).delete()
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()
    
    # Finally delete user
    db.session.delete(user)
    db.session.commit()

    logger.info("Deleted account for user_id=%s", uid)
    return jsonify(message="account deleted"), 200
