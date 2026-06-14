"""
GDPR PII Export & Delete Service

Provides:
- export_user_data: Collect all PII into a structured dict (JSON-serialisable)
- initiate_deletion: Two-step soft-delete → hard-delete workflow
- execute_deletion: Hard-delete user data, preserve GDPR audit trail
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

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
    AdImpression,
)

logger = logging.getLogger("finmind.gdpr")

# ── constants ──────────────────────────────────────────────────────────────────

DELETION_GRACE_DAYS = 30  # days before hard delete executes after initiation
GDPR_ACTION_EXPORT = "GDPR_EXPORT"
GDPR_ACTION_DELETE_INITIATED = "GDPR_DELETE_INITIATED"
GDPR_ACTION_DELETE_CANCELLED = "GDPR_DELETE_CANCELLED"
GDPR_ACTION_DELETE_EXECUTED = "GDPR_DELETE_EXECUTED"


# ── helpers ────────────────────────────────────────────────────────────────────


def _serialize(obj: Any) -> Any:
    """Recursively convert non-serialisable types."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "date") and callable(obj.date):
        return obj.isoformat()
    return obj


def _row_to_dict(row: db.Model) -> dict:
    return {col.name: getattr(row, col.name) for col in row.__table__.columns}


# ── public API ─────────────────────────────────────────────────────────────────


def export_user_data(user_id: int, request_ip: str, user_agent: str) -> dict:
    """
    Collect all PII associated with *user_id* into a structured dict.
    Also writes a GDPR_EXPORT audit record.

    Returns a dict with keys: profile, categories, expenses,
    recurring_expenses, bills, reminders, subscriptions.
    """
    user: User | None = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    categories = db.session.query(Category).filter_by(user_id=user_id).all()
    expenses = db.session.query(Expense).filter_by(user_id=user_id).all()
    recurring = db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    bills = db.session.query(Bill).filter_by(user_id=user_id).all()
    reminders = db.session.query(Reminder).filter_by(user_id=user_id).all()
    subscriptions = db.session.query(UserSubscription).filter_by(user_id=user_id).all()

    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "profile": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": [_serialize(_row_to_dict(c)) for c in categories],
        "expenses": [_serialize(_row_to_dict(e)) for e in expenses],
        "recurring_expenses": [_serialize(_row_to_dict(r)) for r in recurring],
        "bills": [_serialize(_row_to_dict(b)) for b in bills],
        "reminders": [_serialize(_row_to_dict(r)) for r in reminders],
        "subscriptions": [_serialize(_row_to_dict(s)) for s in subscriptions],
    }

    _write_audit(
        user_id=user_id,
        action=GDPR_ACTION_EXPORT,
        detail=f"ip={request_ip} ua={user_agent[:120]}",
    )

    logger.info("GDPR export generated for user_id=%s ip=%s", user_id, request_ip)
    return payload


def export_user_data_csv(user_id: int, request_ip: str, user_agent: str) -> bytes:
    """
    Return a CSV export of expenses for *user_id* as raw bytes.
    """
    expenses = db.session.query(Expense).filter_by(user_id=user_id).all()

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "id",
            "category_id",
            "amount",
            "currency",
            "expense_type",
            "notes",
            "spent_at",
            "created_at",
        ],
    )
    writer.writeheader()
    for e in expenses:
        writer.writerow(
            {
                "id": e.id,
                "category_id": e.category_id,
                "amount": str(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes or "",
                "spent_at": e.spent_at.isoformat() if e.spent_at else "",
                "created_at": e.created_at.isoformat() if e.created_at else "",
            }
        )

    _write_audit(
        user_id=user_id,
        action=GDPR_ACTION_EXPORT,
        detail=f"format=csv ip={request_ip}",
    )

    return buf.getvalue().encode("utf-8")


def initiate_deletion(user_id: int, request_ip: str, user_agent: str) -> dict:
    """
    Begin the two-step deletion workflow.

    Marks the user account for deletion (soft-delete flag via audit record)
    and returns the scheduled_at timestamp after which hard-delete will run.
    """
    user: User | None = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    scheduled_at = datetime.utcnow() + timedelta(days=DELETION_GRACE_DAYS)

    _write_audit(
        user_id=user_id,
        action=GDPR_ACTION_DELETE_INITIATED,
        detail=(
            f"scheduled_at={scheduled_at.isoformat()} "
            f"ip={request_ip} ua={user_agent[:120]}"
        ),
    )

    logger.warning(
        "GDPR deletion initiated user_id=%s scheduled_at=%s ip=%s",
        user_id,
        scheduled_at.isoformat(),
        request_ip,
    )

    return {
        "message": (
            "Deletion scheduled. Your account and all associated data will be "
            f"permanently deleted on {scheduled_at.date().isoformat()} "
            f"({DELETION_GRACE_DAYS}-day grace period). "
            "To cancel, contact support before this date."
        ),
        "scheduled_deletion_at": scheduled_at.isoformat() + "Z",
        "grace_period_days": DELETION_GRACE_DAYS,
    }


def execute_deletion(user_id: int, request_ip: str, user_agent: str) -> dict:
    """
    Hard-delete all user PII.
    GDPR audit log entries are preserved (legally required, 7-year retention).
    Must only be called after grace period has passed or by admin override.
    """
    user: User | None = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    # Preserve audit records by setting user_id = NULL before deleting the user.
    db.session.query(AuditLog).filter_by(user_id=user_id).update(
        {"user_id": None}, synchronize_session=False
    )

    # Delete all associated data in dependency order.
    db.session.query(AdImpression).filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.query(UserSubscription).filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.query(Reminder).filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.query(Bill).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.session.query(Expense).filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.query(RecurringExpense).filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.query(Category).filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.delete(user)
    db.session.commit()

    # Write a final audit entry with no user_id (user is gone).
    _write_audit(
        user_id=None,
        action=GDPR_ACTION_DELETE_EXECUTED,
        detail=f"deleted_user_id={user_id} ip={request_ip} ua={user_agent[:120]}",
    )

    logger.warning(
        "GDPR hard-delete executed for user_id=%s ip=%s", user_id, request_ip
    )

    return {"message": "All personal data has been permanently deleted."}


# ── internal ───────────────────────────────────────────────────────────────────


def _write_audit(
    user_id: int | None,
    action: str,
    detail: str = "",
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=f"{action}: {detail}" if detail else action,
    )
    db.session.add(entry)
    db.session.commit()
