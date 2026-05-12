"""GDPR PII export and delete workflow routes."""

import json
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Expense, Category, Bill, Reminder, RecurringExpense, AuditLog

bp = Blueprint("gdpr", __name__)


@bp.post("/export")
@jwt_required()
def export_data():
    """Generate a full PII export package for the authenticated user."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    export = {
        "exported_at": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "created_at": user.created_at.isoformat(),
        },
        "expenses": _export_expenses(uid),
        "categories": _export_categories(uid),
        "bills": _export_bills(uid),
        "reminders": _export_reminders(uid),
        "recurring_expenses": _export_recurring(uid),
    }

    # Log the export action
    _audit(uid, "pii_export_requested")

    return jsonify(export=export)


@bp.post("/delete")
@jwt_required()
def delete_data():
    """Permanently delete all user data (irreversible)."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    # Require explicit confirmation
    if data.get("confirm") != "DELETE_MY_DATA":
        return jsonify(
            error="Must send {\"confirm\": \"DELETE_MY_DATA\"} to proceed"
        ), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Delete in dependency order
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()

    # Log deletion before removing user (audit trail preserved with null user)
    _audit(uid, "pii_deletion_completed")

    # Delete user last
    db.session.delete(user)
    db.session.commit()

    return jsonify(message="All personal data has been permanently deleted"), 200


@bp.get("/status")
@jwt_required()
def data_status():
    """Show what data exists for the user."""
    uid = int(get_jwt_identity())
    return jsonify(
        data_summary={
            "expenses": db.session.query(Expense).filter_by(user_id=uid).count(),
            "categories": db.session.query(Category).filter_by(user_id=uid).count(),
            "bills": db.session.query(Bill).filter_by(user_id=uid).count(),
            "reminders": db.session.query(Reminder).filter_by(user_id=uid).count(),
            "recurring_expenses": db.session.query(RecurringExpense).filter_by(user_id=uid).count(),
        }
    )


def _export_expenses(uid):
    rows = db.session.query(Expense).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "expense_type": r.expense_type,
            "notes": r.notes,
            "spent_at": r.spent_at.isoformat() if r.spent_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def _export_categories(uid):
    rows = db.session.query(Category).filter_by(user_id=uid).all()
    return [{"id": r.id, "name": r.name, "created_at": r.created_at.isoformat()} for r in rows]


def _export_bills(uid):
    rows = db.session.query(Bill).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "amount": float(r.amount),
            "currency": r.currency,
            "next_due_date": r.next_due_date.isoformat() if r.next_due_date else None,
            "cadence": r.cadence.value if r.cadence else None,
        }
        for r in rows
    ]


def _export_reminders(uid):
    rows = db.session.query(Reminder).filter_by(user_id=uid).all()
    return [
        {"id": r.id, "message": r.message, "send_at": r.send_at.isoformat(), "channel": r.channel}
        for r in rows
    ]


def _export_recurring(uid):
    rows = db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "notes": r.notes,
            "cadence": r.cadence.value if r.cadence else None,
            "start_date": r.start_date.isoformat() if r.start_date else None,
        }
        for r in rows
    ]


def _audit(uid, action):
    log = AuditLog(user_id=uid, action=action)
    db.session.add(log)
    db.session.flush()
