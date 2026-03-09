"""
PII Export & Delete Service — GDPR-ready data portability and erasure.

Provides:
- Export: generates a JSON package of all user PII and associated data
- Delete: irreversibly removes all user data with audit trail
"""

import json
import logging
from datetime import datetime, date
from decimal import Decimal

from ..extensions import db
from ..models import (
    User,
    Category,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    AdImpression,
    UserSubscription,
    AuditLog,
)

logger = logging.getLogger("finmind.pii")


class _JSONEncoder(json.JSONEncoder):
    """Handle datetime, date, and Decimal serialization."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def _serialize_row(row, exclude_cols=None):
    """Convert a SQLAlchemy model instance to a dict."""
    exclude = set(exclude_cols or [])
    result = {}
    for col in row.__table__.columns:
        if col.name in exclude:
            continue
        result[col.name] = getattr(row, col.name)
    return result


def export_user_data(user_id: int) -> dict:
    """
    Generate a complete PII export package for the given user.

    Returns a dict containing all user data, suitable for JSON serialization.
    The export includes: profile, categories, expenses, recurring expenses,
    bills, reminders, ad impressions, subscriptions, and audit logs.
    """
    user = db.session.get(User, user_id)
    if not user:
        return None

    # Collect all user data
    categories = Category.query.filter_by(user_id=user_id).all()
    expenses = Expense.query.filter_by(user_id=user_id).all()
    recurring = RecurringExpense.query.filter_by(user_id=user_id).all()
    bills = Bill.query.filter_by(user_id=user_id).all()
    reminders = Reminder.query.filter_by(user_id=user_id).all()
    ad_impressions = AdImpression.query.filter_by(user_id=user_id).all()
    subscriptions = UserSubscription.query.filter_by(user_id=user_id).all()
    audit_logs = AuditLog.query.filter_by(user_id=user_id).all()

    export = {
        "export_version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "user": _serialize_row(user, exclude_cols=["password_hash"]),
        "categories": [_serialize_row(c) for c in categories],
        "expenses": [_serialize_row(e) for e in expenses],
        "recurring_expenses": [_serialize_row(r) for r in recurring],
        "bills": [_serialize_row(b) for b in bills],
        "reminders": [_serialize_row(r) for r in reminders],
        "ad_impressions": [_serialize_row(a) for a in ad_impressions],
        "subscriptions": [_serialize_row(s) for s in subscriptions],
        "audit_logs": [_serialize_row(a) for a in audit_logs],
    }

    # Log the export action
    db.session.add(
        AuditLog(user_id=user_id, action="pii_export")
    )
    db.session.commit()

    logger.info("PII export generated for user %d", user_id)
    return json.loads(json.dumps(export, cls=_JSONEncoder))


def delete_user_data(user_id: int) -> dict:
    """
    Irreversibly delete all personal data for the given user.

    Deletion order respects foreign key constraints.
    An audit trail entry is created *before* user deletion (with user_id=None
    post-deletion to preserve the log).

    Returns a summary dict with counts of deleted records per table.
    """
    user = db.session.get(User, user_id)
    if not user:
        return None

    summary = {}

    # Delete in dependency order (children first)
    # 1. Reminders (depends on bills)
    count = Reminder.query.filter_by(user_id=user_id).delete()
    summary["reminders"] = count

    # 2. Expenses (depends on categories, recurring_expenses)
    count = Expense.query.filter_by(user_id=user_id).delete()
    summary["expenses"] = count

    # 3. Recurring expenses (depends on categories)
    count = RecurringExpense.query.filter_by(user_id=user_id).delete()
    summary["recurring_expenses"] = count

    # 4. Bills
    count = Bill.query.filter_by(user_id=user_id).delete()
    summary["bills"] = count

    # 5. Categories
    count = Category.query.filter_by(user_id=user_id).delete()
    summary["categories"] = count

    # 6. Ad impressions
    count = AdImpression.query.filter_by(user_id=user_id).delete()
    summary["ad_impressions"] = count

    # 7. User subscriptions
    count = UserSubscription.query.filter_by(user_id=user_id).delete()
    summary["subscriptions"] = count

    # 8. Audit logs for this user (except the deletion record we're about to create)
    count = AuditLog.query.filter_by(user_id=user_id).delete()
    summary["audit_logs"] = count

    # 9. Create deletion audit trail (user_id=None since user will be gone)
    email_hash = str(hash(user.email))  # pseudonymized reference
    db.session.add(
        AuditLog(
            user_id=None,
            action=f"pii_delete:user_hash={email_hash}",
        )
    )

    # 10. Delete the user record itself
    db.session.delete(user)
    summary["user"] = 1

    db.session.commit()

    logger.info(
        "PII deletion completed for user %d: %s",
        user_id,
        summary,
    )
    return summary
