"""PII export & deletion service (GDPR-ready)."""

import csv
import io
import json
from datetime import datetime

from ..extensions import db
from ..models import (
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
    User,
    UserSubscription,
)


def export_user_data(user_id: int) -> dict:
    """Collect all PII for *user_id* into an export package.

    Returns a dict with ``json_export`` (str) and ``csv_export`` (str).
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("user not found")

    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
    }

    expenses = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "category_id": e.category_id,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat(),
        }
        for e in db.session.query(Expense).filter_by(user_id=user_id).all()
    ]

    categories = [
        {"id": c.id, "name": c.name}
        for c in db.session.query(Category).filter_by(user_id=user_id).all()
    ]

    bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value if b.cadence else None,
        }
        for b in db.session.query(Bill).filter_by(user_id=user_id).all()
    ]

    reminders = [
        {
            "id": r.id,
            "message": r.message,
            "send_at": r.send_at.isoformat(),
            "sent": r.sent,
            "channel": r.channel,
        }
        for r in db.session.query(Reminder).filter_by(user_id=user_id).all()
    ]

    recurring = [
        {
            "id": r.id,
            "amount": float(r.amount),
            "notes": r.notes,
            "cadence": r.cadence.value if r.cadence else None,
            "start_date": r.start_date.isoformat(),
        }
        for r in db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    ]

    package = {
        "export_date": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "profile": profile,
        "expenses": expenses,
        "categories": categories,
        "bills": bills,
        "reminders": reminders,
        "recurring_expenses": recurring,
    }

    json_export = json.dumps(package, indent=2, default=str)

    # CSV export of expenses (most common data export request)
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=["id", "amount", "currency", "category_id", "expense_type", "notes", "spent_at"],
    )
    writer.writeheader()
    for e in expenses:
        writer.writerow(e)
    csv_export = csv_buffer.getvalue()

    _log_audit(user_id, "pii_export")

    return {
        "json_export": json_export,
        "csv_export": csv_export,
        "summary": {
            "profile": 1,
            "expenses": len(expenses),
            "categories": len(categories),
            "bills": len(bills),
            "reminders": len(reminders),
            "recurring_expenses": len(recurring),
        },
    }


def delete_user_data(user_id: int) -> dict:
    """Permanently delete all user data (irreversible).

    Preserves a minimal audit log entry for compliance.
    Returns counts of deleted records.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("user not found")

    counts = {}

    # Delete in dependency order (children first)
    counts["reminders"] = (
        db.session.query(Reminder).filter_by(user_id=user_id).delete()
    )
    counts["recurring_expenses"] = (
        db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()
    )
    counts["expenses"] = (
        db.session.query(Expense).filter_by(user_id=user_id).delete()
    )
    counts["bills"] = (
        db.session.query(Bill).filter_by(user_id=user_id).delete()
    )
    counts["categories"] = (
        db.session.query(Category).filter_by(user_id=user_id).delete()
    )
    counts["subscriptions"] = (
        db.session.query(UserSubscription).filter_by(user_id=user_id).delete()
    )

    # Log deletion BEFORE removing user (audit log references user_id)
    _log_audit(user_id, "pii_deletion_complete")

    # Delete the user account itself
    db.session.delete(user)
    counts["user"] = 1

    db.session.commit()

    return counts


def get_audit_log(user_id: int) -> list:
    """Return privacy-related audit log entries for *user_id*."""
    entries = (
        db.session.query(AuditLog)
        .filter_by(user_id=user_id)
        .filter(AuditLog.action.in_(["pii_export", "pii_deletion_requested", "pii_deletion_complete"]))
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    return [
        {
            "id": e.id,
            "action": e.action,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


def _log_audit(user_id: int, action: str) -> None:
    entry = AuditLog(user_id=user_id, action=action)
    db.session.add(entry)
    db.session.flush()
