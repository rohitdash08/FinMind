"""GDPR-compliant PII export and deletion service."""
import logging
from datetime import datetime, timezone
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

logger = logging.getLogger("finmind.gdpr")


def collect_user_data(user_id: int) -> dict:
    """Collect all PII associated with a user for export.

    Returns a serialisable dict containing every piece of personal data
    stored for the given user.
    """
    user = db.session.get(User, user_id)
    if not user:
        return {}

    def _model_to_dict(instance):
        """Convert a SQLAlchemy model instance to a plain dict."""
        return {
            c.key: getattr(instance, c.key)
            for c in db.inspect(instance).mapper.column_attrs
        }

    def _serialize_values(d):
        """Ensure all values are JSON-serialisable."""
        out = {}
        for k, v in d.items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            elif hasattr(v, "isoformat"):  # date objects
                out[k] = v.isoformat()
            elif isinstance(v, (int, float, str, bool)) or v is None:
                out[k] = v
            else:
                out[k] = str(v)
        return out

    categories = db.session.query(Category).filter_by(user_id=user_id).all()
    expenses = db.session.query(Expense).filter_by(user_id=user_id).all()
    recurring = db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    bills = db.session.query(Bill).filter_by(user_id=user_id).all()
    reminders = db.session.query(Reminder).filter_by(user_id=user_id).all()
    ad_impressions = db.session.query(AdImpression).filter_by(user_id=user_id).all()
    subscriptions = db.session.query(UserSubscription).filter_by(user_id=user_id).all()

    return {
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "user": _serialize_values(_model_to_dict(user)),
        "categories": [_serialize_values(_model_to_dict(c)) for c in categories],
        "expenses": [_serialize_values(_model_to_dict(e)) for e in expenses],
        "recurring_expenses": [_serialize_values(_model_to_dict(r)) for r in recurring],
        "bills": [_serialize_values(_model_to_dict(b)) for b in bills],
        "reminders": [_serialize_values(_model_to_dict(r)) for r in reminders],
        "ad_impressions": [_serialize_values(_model_to_dict(a)) for a in ad_impressions],
        "subscriptions": [_serialize_values(_model_to_dict(s)) for s in subscriptions],
    }


def permanently_delete_user(user_id: int) -> bool:
    """Irreversibly delete all data associated with the given user.

    This operation cannot be undone. All related records across every table
    are deleted, and finally the user row itself is removed.

    Returns True if the user existed and was deleted, False otherwise.
    """
    user = db.session.get(User, user_id)
    if not user:
        return False

    # Delete related records in dependency order
    # (Some tables have FK ON DELETE CASCADE, but we are explicit for safety,
    #  especially since SQLite tests may not enforce FK constraints.)
    db.session.query(Reminder).filter_by(user_id=user_id).delete()
    db.session.query(UserSubscription).filter_by(user_id=user_id).delete()
    db.session.query(Bill).filter_by(user_id=user_id).delete()
    db.session.query(Expense).filter_by(user_id=user_id).delete()
    db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()
    db.session.query(Category).filter_by(user_id=user_id).delete()
    # Ad impressions: user_id is nullable, set to NULL rather than delete
    db.session.query(AdImpression).filter_by(user_id=user_id).update(
        {"user_id": None}, synchronize_session="fetch"
    )

    # Finally delete the user row
    db.session.delete(user)
    db.session.commit()
    logger.info("Permanently deleted user_id=%s and all associated data", user_id)
    return True


def log_audit_action(user_id: int | None, action: str, ip_address: str | None = None) -> None:
    """Record a GDPR audit log entry for export/delete operations."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        ip_address=ip_address,
    )
    db.session.add(entry)
    db.session.commit()
    logger.info(
        "GDPR audit log: user_id=%s action=%s ip=%s",
        user_id,
        action,
        ip_address,
    )
