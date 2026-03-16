"""GDPR-ready PII export and deletion service.

Collects all user-owned data across every model and returns it as a
serialisable dictionary. Also provides irreversible account deletion
with full audit-trail logging.
"""

import logging
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

logger = logging.getLogger("finmind.privacy")


def _serialize_date(d):
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.isoformat()
    return d.isoformat()


def export_user_data(user_id: int) -> dict:
    """Return a JSON-serialisable dict of ALL personal data for *user_id*."""
    user = db.session.get(User, user_id)
    if not user:
        return {}

    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": _serialize_date(user.created_at),
    }

    categories = [
        {"id": c.id, "name": c.name, "created_at": _serialize_date(c.created_at)}
        for c in Category.query.filter_by(user_id=user_id).all()
    ]

    expenses = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "spent_at": _serialize_date(e.spent_at),
            "category_id": e.category_id,
            "created_at": _serialize_date(e.created_at),
        }
        for e in Expense.query.filter_by(user_id=user_id).all()
    ]

    recurring = [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "expense_type": r.expense_type,
            "notes": r.notes,
            "cadence": r.cadence.value if r.cadence else None,
            "start_date": _serialize_date(r.start_date),
            "end_date": _serialize_date(r.end_date),
            "active": r.active,
            "category_id": r.category_id,
            "created_at": _serialize_date(r.created_at),
        }
        for r in RecurringExpense.query.filter_by(user_id=user_id).all()
    ]

    bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": _serialize_date(b.next_due_date),
            "cadence": b.cadence.value if b.cadence else None,
            "autopay_enabled": b.autopay_enabled,
            "active": b.active,
            "created_at": _serialize_date(b.created_at),
        }
        for b in Bill.query.filter_by(user_id=user_id).all()
    ]

    reminders = [
        {
            "id": rm.id,
            "bill_id": rm.bill_id,
            "message": rm.message,
            "send_at": _serialize_date(rm.send_at),
            "sent": rm.sent,
            "channel": rm.channel,
        }
        for rm in Reminder.query.filter_by(user_id=user_id).all()
    ]

    subscriptions = [
        {
            "id": s.id,
            "plan_id": s.plan_id,
            "active": s.active,
            "started_at": _serialize_date(s.started_at),
        }
        for s in UserSubscription.query.filter_by(user_id=user_id).all()
    ]

    audit_logs = [
        {
            "id": a.id,
            "action": a.action,
            "created_at": _serialize_date(a.created_at),
        }
        for a in AuditLog.query.filter_by(user_id=user_id).all()
    ]

    return {
        "export_version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "profile": profile,
        "categories": categories,
        "expenses": expenses,
        "recurring_expenses": recurring,
        "bills": bills,
        "reminders": reminders,
        "subscriptions": subscriptions,
        "audit_logs": audit_logs,
    }


def delete_user_data(user_id: int) -> bool:
    """Permanently and irreversibly delete all data for *user_id*.

    Creates a final audit log entry (anonymised) before removing
    the user row (cascades handle child records).
    Returns True on success, False if user not found.
    """
    user = db.session.get(User, user_id)
    if not user:
        return False

    # Log the deletion request before wiping data
    db.session.add(
        AuditLog(user_id=None, action=f"GDPR_DELETE:user_id={user_id}")
    )

    # Delete child records explicitly for databases without CASCADE support
    Reminder.query.filter_by(user_id=user_id).delete()
    Expense.query.filter_by(user_id=user_id).delete()
    RecurringExpense.query.filter_by(user_id=user_id).delete()
    Bill.query.filter_by(user_id=user_id).delete()
    Category.query.filter_by(user_id=user_id).delete()
    UserSubscription.query.filter_by(user_id=user_id).delete()
    AuditLog.query.filter_by(user_id=user_id).delete()

    db.session.delete(user)
    db.session.commit()

    logger.info("GDPR delete completed for user_id=%s", user_id)
    return True
