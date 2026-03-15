"""GDPR PII export & deletion service.

Handles:
- Collecting all PII owned by a user across every table.
- Generating a structured JSON export package.
- Soft-delete → hard-delete lifecycle with confirmation & grace period.
- Immutable GDPR-specific audit trail logging.
"""

from datetime import datetime
import json
import logging
from flask import request as flask_request

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
    GDPRAuditLog,
    GDPRAction,
    DeletionRequest,
    DeletionStatus,
)

logger = logging.getLogger("finmind.gdpr")

# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def _client_ip():
    """Extract client IP from current request context."""
    try:
        return flask_request.remote_addr
    except RuntimeError:
        return None


def _client_ua():
    """Extract User-Agent from current request context."""
    try:
        return str(flask_request.user_agent)[:500]
    except RuntimeError:
        return None


def log_gdpr_event(user_id, user_email, action, details=None):
    """Write an immutable GDPR audit record."""
    entry = GDPRAuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action.value if isinstance(action, GDPRAction) else action,
        details=details or {},
        ip_address=_client_ip(),
        user_agent=_client_ua(),
    )
    db.session.add(entry)
    db.session.commit()
    logger.info("GDPR audit: user=%s action=%s", user_id, action)
    return entry


# ---------------------------------------------------------------------------
# PII Export
# ---------------------------------------------------------------------------

def _serialize_rows(rows, exclude=None):
    """Convert a list of SQLAlchemy model instances to dicts."""
    exclude = exclude or set()
    result = []
    for row in rows:
        d = {}
        for col in row.__table__.columns:
            if col.name in exclude:
                continue
            val = getattr(row, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            elif hasattr(val, "isoformat"):
                val = val.isoformat()
            elif hasattr(val, "value"):  # Enum
                val = val.value
            d[col.name] = val
        result.append(d)
    return result


def export_user_pii(user_id):
    """Collect all PII for *user_id* into a structured dict.

    Returns a dict ready to be serialised as JSON. Excludes password
    hashes to avoid leaking credential material.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return None

    package = {
        "export_generated_at": datetime.utcnow().isoformat(),
        "user_id": user.id,
        "profile": {
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
        },
        "categories": _serialize_rows(
            Category.query.filter_by(user_id=user_id).all()
        ),
        "expenses": _serialize_rows(
            Expense.query.filter_by(user_id=user_id).all()
        ),
        "recurring_expenses": _serialize_rows(
            RecurringExpense.query.filter_by(user_id=user_id).all()
        ),
        "bills": _serialize_rows(
            Bill.query.filter_by(user_id=user_id).all()
        ),
        "reminders": _serialize_rows(
            Reminder.query.filter_by(user_id=user_id).all()
        ),
        "subscriptions": _serialize_rows(
            UserSubscription.query.filter_by(user_id=user_id).all()
        ),
        "ad_impressions": _serialize_rows(
            AdImpression.query.filter_by(user_id=user_id).all()
        ),
        "audit_logs": _serialize_rows(
            AuditLog.query.filter_by(user_id=user_id).all()
        ),
    }

    log_gdpr_event(
        user_id, user.email, GDPRAction.EXPORT_COMPLETED,
        {"record_counts": {k: len(v) for k, v in package.items()
                           if isinstance(v, list)}},
    )
    return package


# ---------------------------------------------------------------------------
# Deletion workflow
# ---------------------------------------------------------------------------

def request_deletion(user_id, reason=None):
    """Start a deletion request.  Returns (request, error_message)."""
    user = db.session.get(User, user_id)
    if user is None:
        return None, "user not found"

    if user.is_deleted:
        return None, "account already deleted"

    # Check for an existing active request
    active = DeletionRequest.query.filter(
        DeletionRequest.user_id == user_id,
        DeletionRequest.status.in_([
            DeletionStatus.PENDING.value,
            DeletionStatus.CONFIRMED.value,
            DeletionStatus.PROCESSING.value,
        ]),
    ).first()
    if active:
        return None, "deletion already in progress"

    req = DeletionRequest.create_request(user_id, reason)
    db.session.add(req)
    db.session.commit()

    log_gdpr_event(
        user_id, user.email, GDPRAction.DELETION_REQUESTED,
        {"request_id": req.id, "reason": reason,
         "grace_period_ends_at": req.grace_period_ends_at.isoformat()},
    )
    return req, None


def confirm_deletion(token):
    """Confirm a pending deletion via token.  Returns (request, error)."""
    req = DeletionRequest.query.filter_by(
        confirmation_token=token,
        status=DeletionStatus.PENDING.value,
    ).first()
    if req is None:
        return None, "invalid or expired confirmation token"

    user = db.session.get(User, req.user_id)
    if user is None:
        return None, "user not found"

    req.status = DeletionStatus.CONFIRMED.value
    req.confirmed_at = datetime.utcnow()
    db.session.commit()

    log_gdpr_event(
        req.user_id, user.email, GDPRAction.DELETION_CONFIRMED,
        {"request_id": req.id},
    )
    return req, None


def cancel_deletion(user_id):
    """Cancel any pending/confirmed deletion request.  Returns (ok, error)."""
    req = DeletionRequest.query.filter(
        DeletionRequest.user_id == user_id,
        DeletionRequest.status.in_([
            DeletionStatus.PENDING.value,
            DeletionStatus.CONFIRMED.value,
        ]),
    ).first()
    if req is None:
        return False, "no active deletion request"

    user = db.session.get(User, req.user_id)
    email = user.email if user else "unknown"

    req.status = DeletionStatus.CANCELLED.value
    db.session.commit()

    log_gdpr_event(req.user_id, email, GDPRAction.DELETION_CANCELLED,
                   {"request_id": req.id})
    return True, None


def execute_deletion(user_id):
    """Permanently erase all user data (hard-delete).

    Call only after confirmation + grace period has elapsed. Removes user
    rows from every table while preserving GDPR audit logs (they store
    ``user_email`` independently and the FK is nullable).
    """
    user = db.session.get(User, user_id)
    if user is None:
        return False, "user not found"

    email = user.email

    req = DeletionRequest.query.filter(
        DeletionRequest.user_id == user_id,
        DeletionRequest.status == DeletionStatus.CONFIRMED.value,
    ).first()
    if req is None:
        return False, "no confirmed deletion request"

    # Check grace period
    if datetime.utcnow() < req.grace_period_ends_at:
        return False, "grace period has not elapsed"

    req.status = DeletionStatus.PROCESSING.value
    db.session.commit()

    try:
        # Delete in dependency order
        Reminder.query.filter_by(user_id=user_id).delete()
        AdImpression.query.filter_by(user_id=user_id).delete()
        UserSubscription.query.filter_by(user_id=user_id).delete()
        Expense.query.filter_by(user_id=user_id).delete()
        RecurringExpense.query.filter_by(user_id=user_id).delete()
        Bill.query.filter_by(user_id=user_id).delete()
        Category.query.filter_by(user_id=user_id).delete()
        AuditLog.query.filter_by(user_id=user_id).delete()
        DeletionRequest.query.filter_by(user_id=user_id).delete()

        # Soft-delete user row (keep for FK integrity in gdpr_audit_logs)
        user.is_deleted = True
        user.deleted_at = datetime.utcnow()
        user.email = f"deleted-{user_id}@removed.invalid"
        user.password_hash = "REDACTED"
        db.session.commit()

        log_gdpr_event(
            user_id, email, GDPRAction.DELETION_COMPLETED,
            {"tables_cleared": [
                "reminders", "ad_impressions", "user_subscriptions",
                "expenses", "recurring_expenses", "bills", "categories",
                "audit_logs", "deletion_requests",
            ]},
        )
        return True, None
    except Exception as exc:
        db.session.rollback()
        log_gdpr_event(
            user_id, email, GDPRAction.DELETION_FAILED,
            {"error": str(exc)},
        )
        logger.exception("Hard-delete failed for user %s", user_id)
        return False, str(exc)


def get_deletion_status(user_id):
    """Return the latest deletion request for a user, or None."""
    return (
        DeletionRequest.query
        .filter_by(user_id=user_id)
        .order_by(DeletionRequest.created_at.desc())
        .first()
    )
