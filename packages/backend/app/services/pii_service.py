"""PII Export & Delete Service — GDPR-ready (Issue #76).

Handles:
- Collecting all personal data for a user into a JSON-serialisable dict.
- Irreversibly deleting all user data from every table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

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


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def build_export_package(user_id: int) -> dict[str, Any]:
    """Collect all PII/personal data for *user_id* and return as a dict.

    The returned structure is safe to serialise directly to JSON.
    """
    user: User | None = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    # ---- profile ----
    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": _dt(user.created_at),
    }

    # ---- categories ----
    categories = [
        {"id": c.id, "name": c.name, "created_at": _dt(c.created_at)}
        for c in db.session.query(Category).filter_by(user_id=user_id).all()
    ]

    # ---- expenses ----
    expenses = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "category_id": e.category_id,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat() if e.spent_at else None,
            "created_at": _dt(e.created_at),
        }
        for e in db.session.query(Expense).filter_by(user_id=user_id).all()
    ]

    # ---- recurring expenses ----
    recurring = [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "expense_type": r.expense_type,
            "category_id": r.category_id,
            "notes": r.notes,
            "cadence": r.cadence.value if r.cadence else None,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "active": r.active,
            "created_at": _dt(r.created_at),
        }
        for r in db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    ]

    # ---- bills ----
    bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
            "cadence": b.cadence.value if b.cadence else None,
            "autopay_enabled": b.autopay_enabled,
            "channel_whatsapp": b.channel_whatsapp,
            "channel_email": b.channel_email,
            "active": b.active,
            "created_at": _dt(b.created_at),
        }
        for b in db.session.query(Bill).filter_by(user_id=user_id).all()
    ]

    # ---- reminders ----
    reminders = [
        {
            "id": rm.id,
            "bill_id": rm.bill_id,
            "message": rm.message,
            "send_at": _dt(rm.send_at),
            "sent": rm.sent,
            "channel": rm.channel,
        }
        for rm in db.session.query(Reminder).filter_by(user_id=user_id).all()
    ]

    # ---- subscriptions ----
    subscriptions = [
        {
            "id": s.id,
            "plan_id": s.plan_id,
            "active": s.active,
            "started_at": _dt(s.started_at),
        }
        for s in db.session.query(UserSubscription).filter_by(user_id=user_id).all()
    ]

    # ---- ad impressions ----
    impressions = [
        {
            "id": a.id,
            "placement": a.placement,
            "created_at": _dt(a.created_at),
        }
        for a in db.session.query(AdImpression).filter_by(user_id=user_id).all()
    ]

    # ---- own audit trail ----
    audit_trail = [
        {
            "id": al.id,
            "action": al.action,
            "details": al.details,
            "ip_address": al.ip_address,
            "created_at": _dt(al.created_at),
        }
        for al in db.session.query(AuditLog).filter_by(user_id=user_id).all()
    ]

    return {
        "export_generated_at": datetime.utcnow().isoformat() + "Z",
        "profile": profile,
        "categories": categories,
        "expenses": expenses,
        "recurring_expenses": recurring,
        "bills": bills,
        "reminders": reminders,
        "subscriptions": subscriptions,
        "ad_impressions": impressions,
        "audit_trail": audit_trail,
    }


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def delete_user_permanently(user_id: int) -> dict[str, int]:
    """Irreversibly delete *all* data belonging to *user_id*.

    Returns a summary dict with the row-counts deleted per table.
    Raises ValueError if the user does not exist.
    The function commits the transaction on success; rolls back on error.
    """
    user: User | None = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    deleted: dict[str, int] = {}

    try:
        # Delete in dependency order (children first)
        deleted["reminders"] = (
            db.session.query(Reminder).filter_by(user_id=user_id).delete()
        )
        deleted["bills"] = (
            db.session.query(Bill).filter_by(user_id=user_id).delete()
        )
        deleted["expenses"] = (
            db.session.query(Expense).filter_by(user_id=user_id).delete()
        )
        deleted["recurring_expenses"] = (
            db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()
        )
        deleted["categories"] = (
            db.session.query(Category).filter_by(user_id=user_id).delete()
        )
        deleted["subscriptions"] = (
            db.session.query(UserSubscription).filter_by(user_id=user_id).delete()
        )
        deleted["ad_impressions"] = (
            db.session.query(AdImpression).filter_by(user_id=user_id).delete()
        )
        # Null-out audit log user_id references (preserve the audit trail itself)
        deleted["audit_logs_anonymised"] = (
            db.session.query(AuditLog)
            .filter(AuditLog.user_id == user_id)
            .update({"user_id": None}, synchronize_session="fetch")
        )
        # Finally delete the user record
        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return deleted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601 string (UTC, Z suffix)."""
    if value is None:
        return None
    return value.isoformat() + "Z"
