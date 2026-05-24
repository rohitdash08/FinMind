"""GDPR PII Export and Account Deletion service.

Public API
----------
build_export_package(uid) -> dict
    Collect all personal data for a user into a serialisable dict.

delete_user_data(uid) -> None
    Irreversibly delete every row belonging to *uid*, log the event,
    and best-effort revoke Redis refresh tokens.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

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

logger = logging.getLogger("finmind.gdpr")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _fmt(val) -> str | None:
    """Convert datetime / date to ISO-8601 string, or return None."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _expense_row(e: Expense) -> dict:
    return {
        "id": e.id,
        "amount": float(e.amount),
        "currency": e.currency,
        "expense_type": e.expense_type,
        "category_id": e.category_id,
        "description": e.notes or "",
        "date": _fmt(e.spent_at),
        "created_at": _fmt(e.created_at),
    }


def _recurring_row(r: RecurringExpense) -> dict:
    return {
        "id": r.id,
        "amount": float(r.amount),
        "currency": r.currency,
        "expense_type": r.expense_type,
        "category_id": r.category_id,
        "description": r.notes,
        "cadence": r.cadence.value,
        "start_date": _fmt(r.start_date),
        "end_date": _fmt(r.end_date),
        "active": r.active,
        "created_at": _fmt(r.created_at),
    }


def _bill_row(b: Bill) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "amount": float(b.amount),
        "currency": b.currency,
        "next_due_date": _fmt(b.next_due_date),
        "cadence": b.cadence.value,
        "autopay_enabled": b.autopay_enabled,
        "active": b.active,
        "created_at": _fmt(b.created_at),
    }


def _reminder_row(r: Reminder) -> dict:
    return {
        "id": r.id,
        "bill_id": r.bill_id,
        "message": r.message,
        "send_at": _fmt(r.send_at),
        "sent": r.sent,
        "channel": r.channel,
    }


def _category_row(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": _fmt(c.created_at),
    }


def _subscription_row(s: UserSubscription) -> dict:
    return {
        "id": s.id,
        "plan_id": s.plan_id,
        "active": s.active,
        "started_at": _fmt(s.started_at),
    }


# ---------------------------------------------------------------------------
# Public: build export package
# ---------------------------------------------------------------------------

def build_export_package(uid: int) -> dict:
    """Return all personal data for *uid* as a plain serialisable dict.

    The returned dict is safe to pass directly to ``flask.jsonify`` or
    written to a file.
    """
    user = db.session.get(User, uid)
    if not user:
        raise ValueError(f"User {uid} not found")

    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at.desc())
        .all()
    )
    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=uid)
        .order_by(RecurringExpense.start_date.desc())
        .all()
    )
    bills = (
        db.session.query(Bill)
        .filter_by(user_id=uid)
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    reminders = (
        db.session.query(Reminder)
        .filter_by(user_id=uid)
        .order_by(Reminder.send_at.asc())
        .all()
    )
    categories = (
        db.session.query(Category)
        .filter_by(user_id=uid)
        .order_by(Category.name.asc())
        .all()
    )
    subscriptions = (
        db.session.query(UserSubscription)
        .filter_by(user_id=uid)
        .all()
    )

    return {
        "schema_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "email": user.email,
            "preferred_currency": user.preferred_currency or "INR",
            "role": user.role,
            "created_at": _fmt(user.created_at),
        },
        "expenses": [_expense_row(e) for e in expenses],
        "recurring_expenses": [_recurring_row(r) for r in recurring],
        "bills": [_bill_row(b) for b in bills],
        "reminders": [_reminder_row(r) for r in reminders],
        "categories": [_category_row(c) for c in categories],
        "subscriptions": [_subscription_row(s) for s in subscriptions],
        "counts": {
            "expenses": len(expenses),
            "recurring_expenses": len(recurring),
            "bills": len(bills),
            "reminders": len(reminders),
            "categories": len(categories),
            "subscriptions": len(subscriptions),
        },
    }


# ---------------------------------------------------------------------------
# Public: delete user data
# ---------------------------------------------------------------------------

def delete_user_data(uid: int) -> None:
    """Irreversibly delete all data belonging to *uid*.

    Deletion order avoids FK violations on databases that enforce
    constraints at the row level (e.g. SQLite with FK pragma on).

    Steps
    -----
    1. Log deletion intent to the audit trail.
    2. Delete child rows in safe dependency order.
    3. Delete the user row itself.
    4. Best-effort revoke Redis refresh tokens for this user.
    """
    user = db.session.get(User, uid)
    if not user:
        raise ValueError(f"User {uid} not found")

    email_snapshot = user.email  # capture before deletion for logging

    # 1. Audit trail — written before any deletion so it survives a partial failure.
    audit = AuditLog(
        user_id=uid,
        action=f"account_deleted:{email_snapshot}",
    )
    db.session.add(audit)
    db.session.flush()  # write to DB but don't commit yet

    # 2. Delete in dependency order
    # Reminders first (reference both users and bills)
    db.session.query(Reminder).filter_by(user_id=uid).delete(synchronize_session=False)
    # Expenses (reference recurring_expenses and categories)
    db.session.query(Expense).filter_by(user_id=uid).delete(synchronize_session=False)
    # Recurring expenses (reference categories)
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete(
        synchronize_session=False
    )
    # Bills
    db.session.query(Bill).filter_by(user_id=uid).delete(synchronize_session=False)
    # Subscriptions
    db.session.query(UserSubscription).filter_by(user_id=uid).delete(
        synchronize_session=False
    )
    # Ad impressions (nullable FK — delete for full erasure)
    db.session.query(AdImpression).filter_by(user_id=uid).delete(
        synchronize_session=False
    )
    # Audit logs (nullable FK — delete all except the one we just wrote)
    db.session.query(AuditLog).filter(
        AuditLog.user_id == uid,
        AuditLog.id != audit.id,
    ).delete(synchronize_session=False)
    # Categories
    db.session.query(Category).filter_by(user_id=uid).delete(synchronize_session=False)

    # 3. Delete the user row
    db.session.delete(user)
    db.session.commit()

    logger.info("Account deleted uid=%s email=%s", uid, email_snapshot)

    # 4. Best-effort Redis refresh-token revocation
    _revoke_redis_tokens(uid)


def _revoke_redis_tokens(uid: int) -> None:
    """Scan Redis for refresh tokens belonging to *uid* and delete them.

    Non-fatal: if Redis is unavailable the active access token expires
    within the configured JWT_ACCESS_TOKEN_EXPIRES window (default 15 min)
    and any refresh token will fail the user-existence check on /auth/refresh.
    """
    try:
        from ..extensions import redis_client

        pattern = "auth:refresh:*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
            for key in keys:
                if redis_client.get(key) == str(uid):
                    redis_client.delete(key)
                    deleted += 1
            if cursor == 0:
                break
        if deleted:
            logger.info("Revoked %d Redis refresh token(s) for uid=%s", deleted, uid)
    except Exception:
        logger.warning(
            "Redis token revocation skipped for uid=%s (Redis unavailable)", uid
        )
