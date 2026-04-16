from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Category, Expense, RecurringExpense, Bill, Reminder, AuditLog
import json
import csv
import io
from datetime import datetime

bp = Blueprint("privacy", __name__)


def _log_audit(user_id, action):
    """Record an audit log entry."""
    entry = AuditLog(user_id=user_id, action=action)
    db.session.add(entry)
    db.session.commit()


def _collect_user_data(user_id):
    """Gather all personal data for a user."""
    user = db.session.get(User, user_id)
    if not user:
        return None

    categories = Category.query.filter_by(user_id=user_id).all()
    expenses = Expense.query.filter_by(user_id=user_id).all()
    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    bills = Bill.query.filter_by(user_id=user_id).all()
    reminders = Reminder.query.filter_by(user_id=user_id).all()

    return {
        "profile": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": [
            {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
            for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "amount": str(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
                "category_id": e.category_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in expenses
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "amount": str(r.amount),
                "currency": r.currency,
                "expense_type": r.expense_type,
                "notes": r.notes,
                "cadence": str(r.cadence),
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
                "amount": str(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
                "cadence": str(b.cadence),
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
        "export_metadata": {
            "exported_at": datetime.utcnow().isoformat(),
            "format_version": "1.0",
            "gdpr_article": "Article 20 - Right to data portability",
        },
    }


@bp.route("/export", methods=["GET"])
@jwt_required()
def export_data():
    """
    Export all personal data as JSON (GDPR Article 20 - Right to data portability).
    Accepts ?format=csv for CSV export.
    """
    user_id = get_jwt_identity()
    data = _collect_user_data(user_id)
    if not data:
        return jsonify(error="User not found"), 404

    fmt = request.args.get("format", "json").lower()
    _log_audit(user_id, f"DATA_EXPORT_REQUESTED:{fmt}")

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Section", "Field", "Value"])
        for section, items in data.items():
            if section == "export_metadata":
                for k, v in items.items():
                    writer.writerow([section, k, v])
            elif section == "profile":
                for k, v in items.items():
                    writer.writerow([section, k, v])
            elif isinstance(items, list):
                for item in items:
                    for k, v in item.items():
                        writer.writerow([section, k, v])
        csv_data = output.getvalue()
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=finmind-data-export.csv"},
        )

    return Response(
        json.dumps(data, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=finmind-data-export.json"},
    )


@bp.route("/delete", methods=["POST"])
@jwt_required()
def delete_account():
    """
    Permanently delete all user data (GDPR Article 17 - Right to erasure).
    Requires {"confirm": "DELETE"} in request body.
    """
    user_id = get_jwt_identity()
    body = request.get_json() or {}

    if body.get("confirm") != "DELETE":
        return jsonify(
            error="Confirmation required",
            message='Send {"confirm": "DELETE"} to proceed',
        ), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error="User not found"), 404

    try:
        # Delete in correct order (respecting foreign keys)
        Reminder.query.filter_by(user_id=user_id).delete()
        Expense.query.filter_by(user_id=user_id).delete()
        RecurringExpense.query.filter_by(user_id=user_id).delete()
        Bill.query.filter_by(user_id=user_id).delete()
        Category.query.filter_by(user_id=user_id).delete()

        # Audit log BEFORE deleting user (so we have the record)
        _log_audit(user_id, "ACCOUNT_DELETED:all_pii_erased")

        # Finally delete the user
        db.session.delete(user)
        db.session.commit()

        return jsonify(
            status="deleted",
            message="All personal data has been permanently erased",
            deleted_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        db.session.rollback()
        return jsonify(error=f"Deletion failed: {str(e)}"), 500
