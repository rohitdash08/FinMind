"""GDPR PII export and deletion service.

Implements:
- Full data export (JSON package with all user-owned records)
- Account deletion with a 30-day grace period
- Data anonymization as an alternative to full deletion
- Immutable GDPR audit trail logging
"""

import json
import logging
from datetime import datetime, timedelta

from ..extensions import db, redis_client
from ..models import (
    Bill,
    Category,
    DeletionRequest,
    Expense,
    GdprAuditLog,
    RecurringExpense,
    Reminder,
    User,
    UserSubscription,
    AdImpression,
    AuditLog,
)

logger = logging.getLogger("finmind.gdpr")

GRACE_PERIOD_DAYS = 30


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def _log_gdpr_action(
    user_id: int,
    action: str,
    status: str = "completed",
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict | None = None,
):
    entry = GdprAuditLog(
        user_id=user_id,
        action=action,
        status=status,
        ip_address=ip_address,
        user_agent=user_agent,
        details=json.dumps(details) if details else None,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


# ---------------------------------------------------------------------------
# Data export
# ---------------------------------------------------------------------------


def export_user_data(user_id: int, ip: str | None = None, ua: str | None = None) -> dict:
    """Build a full PII export package for a user.

    Returns a dict with every data category the user owns, ready to be
    serialised as JSON or converted to CSV on the caller side.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("user not found")

    package = {
        "export_generated_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": _export_categories(user_id),
        "expenses": _export_expenses(user_id),
        "recurring_expenses": _export_recurring(user_id),
        "bills": _export_bills(user_id),
        "reminders": _export_reminders(user_id),
        "subscriptions": _export_subscriptions(user_id),
        "audit_logs": _export_audit_logs(user_id),
    }

    _log_gdpr_action(
        user_id,
        action="EXPORT",
        ip_address=ip,
        user_agent=ua,
        details={"record_counts": {k: len(v) for k, v in package.items() if isinstance(v, list)}},
    )
    db.session.commit()

    logger.info("Exported PII for user_id=%s", user_id)
    return package


def _export_categories(uid: int) -> list[dict]:
    rows = db.session.query(Category).filter_by(user_id=uid).all()
    return [
        {"id": r.id, "name": r.name, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


def _export_expenses(uid: int) -> list[dict]:
    rows = db.session.query(Expense).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "expense_type": r.expense_type,
            "category_id": r.category_id,
            "notes": r.notes,
            "spent_at": r.spent_at.isoformat() if r.spent_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _export_recurring(uid: int) -> list[dict]:
    rows = db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    return [
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
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _export_bills(uid: int) -> list[dict]:
    rows = db.session.query(Bill).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "amount": float(r.amount),
            "currency": r.currency,
            "next_due_date": r.next_due_date.isoformat() if r.next_due_date else None,
            "cadence": r.cadence.value if r.cadence else None,
            "autopay_enabled": r.autopay_enabled,
            "channel_email": r.channel_email,
            "channel_whatsapp": r.channel_whatsapp,
            "active": r.active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _export_reminders(uid: int) -> list[dict]:
    rows = db.session.query(Reminder).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "bill_id": r.bill_id,
            "message": r.message,
            "send_at": r.send_at.isoformat() if r.send_at else None,
            "sent": r.sent,
            "channel": r.channel,
        }
        for r in rows
    ]


def _export_subscriptions(uid: int) -> list[dict]:
    rows = db.session.query(UserSubscription).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "plan_id": r.plan_id,
            "active": r.active,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        }
        for r in rows
    ]


def _export_audit_logs(uid: int) -> list[dict]:
    rows = db.session.query(AuditLog).filter_by(user_id=uid).all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Account deletion
# ---------------------------------------------------------------------------


def request_deletion(
    user_id: int,
    reason: str | None = None,
    ip: str | None = None,
    ua: str | None = None,
) -> dict:
    """Initiate a deletion request with a grace period.

    Returns status info including the scheduled hard-delete date.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("user not found")

    existing = db.session.query(DeletionRequest).filter_by(user_id=user_id, cancelled=False).first()
    if existing and not existing.cancelled:
        return {
            "status": "already_pending",
            "scheduled_at": existing.scheduled_at.isoformat() + "Z",
            "message": "A deletion request is already pending.",
        }

    scheduled = datetime.utcnow() + timedelta(days=GRACE_PERIOD_DAYS)
    req = DeletionRequest(
        user_id=user_id,
        reason=reason,
        scheduled_at=scheduled,
    )
    db.session.add(req)

    _log_gdpr_action(
        user_id,
        action="DELETE_REQUEST",
        status="pending",
        ip_address=ip,
        user_agent=ua,
        details={"reason": reason, "grace_period_days": GRACE_PERIOD_DAYS},
    )
    db.session.commit()

    logger.info("Deletion requested for user_id=%s, scheduled_at=%s", user_id, scheduled)
    return {
        "status": "pending",
        "scheduled_at": scheduled.isoformat() + "Z",
        "grace_period_days": GRACE_PERIOD_DAYS,
        "message": f"Your account is scheduled for deletion on {scheduled.strftime('%Y-%m-%d')}. "
        f"You may cancel within the {GRACE_PERIOD_DAYS}-day grace period.",
    }


def cancel_deletion(user_id: int, ip: str | None = None, ua: str | None = None) -> dict:
    """Cancel a pending deletion request during the grace period."""
    req = (
        db.session.query(DeletionRequest)
        .filter_by(user_id=user_id, cancelled=False, confirmed=False)
        .first()
    )
    if not req:
        return {"status": "not_found", "message": "No pending deletion request found."}

    req.cancelled = True
    _log_gdpr_action(user_id, action="DELETE_CANCEL", ip_address=ip, user_agent=ua)
    db.session.commit()

    logger.info("Deletion cancelled for user_id=%s", user_id)
    return {"status": "cancelled", "message": "Deletion request has been cancelled."}


def confirm_deletion(user_id: int, ip: str | None = None, ua: str | None = None) -> dict:
    """Immediately execute irreversible account deletion (skips grace period).

    Cascading delete removes all user-owned data. The GDPR audit log
    entries are intentionally preserved for compliance.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("user not found")

    # Record the audit trail BEFORE deletion (user_id column has no FK)
    _log_gdpr_action(
        user_id,
        action="DELETE_CONFIRM",
        ip_address=ip,
        user_agent=ua,
        details={"email_hash": _hash_email(user.email)},
    )

    # Cascade delete across every user-owned table
    _hard_delete_user_data(user_id)

    # Mark any pending deletion request as confirmed
    pending = db.session.query(DeletionRequest).filter_by(user_id=user_id).all()
    for p in pending:
        db.session.delete(p)

    # Finally delete the user row
    db.session.delete(user)
    db.session.commit()

    # Invalidate all caches for this user
    _invalidate_user_caches(user_id)

    logger.info("Account permanently deleted for user_id=%s", user_id)
    return {"status": "deleted", "message": "Your account and all associated data have been permanently deleted."}


def _hard_delete_user_data(user_id: int):
    """Delete all rows owned by user_id across every table."""
    db.session.query(Reminder).filter_by(user_id=user_id).delete()
    db.session.query(Expense).filter_by(user_id=user_id).delete()
    db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()
    db.session.query(Bill).filter_by(user_id=user_id).delete()
    db.session.query(Category).filter_by(user_id=user_id).delete()
    db.session.query(UserSubscription).filter_by(user_id=user_id).delete()
    db.session.query(AdImpression).filter_by(user_id=user_id).delete()
    db.session.query(AuditLog).filter_by(user_id=user_id).delete()
    db.session.query(DeletionRequest).filter_by(user_id=user_id).delete()


def _invalidate_user_caches(user_id: int):
    """Best-effort removal of all Redis keys for the user."""
    try:
        patterns = [
            f"user:{user_id}:*",
            f"insights:{user_id}:*",
            f"auth:refresh:*",  # broader sweep – acceptable
        ]
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        logger.warning("Cache invalidation failed for user_id=%s", user_id, exc_info=True)


# ---------------------------------------------------------------------------
# Data anonymization (alternative to full deletion)
# ---------------------------------------------------------------------------


def anonymize_user(user_id: int, ip: str | None = None, ua: str | None = None) -> dict:
    """Replace PII with anonymized placeholders while keeping aggregated data.

    This satisfies GDPR right-to-erasure for users who want their
    financial history preserved in an anonymous form.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("user not found")

    anon_email = f"anon-{user_id}@deleted.finmind.local"
    user.email = anon_email
    user.password_hash = "ANONYMIZED"

    # Scrub free-text fields that might contain PII
    expenses = db.session.query(Expense).filter_by(user_id=user_id).all()
    for e in expenses:
        if e.notes:
            e.notes = "[redacted]"

    recurring = db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    for r in recurring:
        if r.notes:
            r.notes = "[redacted]"

    bills = db.session.query(Bill).filter_by(user_id=user_id).all()
    for b in bills:
        b.name = "[redacted]"

    reminders = db.session.query(Reminder).filter_by(user_id=user_id).all()
    for r in reminders:
        r.message = "[redacted]"

    _log_gdpr_action(
        user_id,
        action="ANONYMIZE",
        ip_address=ip,
        user_agent=ua,
        details={"original_email_hash": _hash_email(user.email)},
    )
    db.session.commit()

    _invalidate_user_caches(user_id)
    logger.info("User anonymized user_id=%s", user_id)
    return {"status": "anonymized", "message": "Your personal data has been anonymized."}


# ---------------------------------------------------------------------------
# Admin: GDPR audit log viewer
# ---------------------------------------------------------------------------


def get_gdpr_audit_logs(
    user_id: int | None = None, page: int = 1, page_size: int = 50
) -> list[dict]:
    """Return GDPR audit log entries, optionally filtered by user."""
    q = db.session.query(GdprAuditLog)
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    rows = (
        q.order_by(GdprAuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "action": r.action,
            "status": r.status,
            "ip_address": r.ip_address,
            "user_agent": r.user_agent,
            "details": json.loads(r.details) if r.details else None,
            "created_at": r.created_at.isoformat() + "Z",
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_email(email: str) -> str:
    """One-way hash of the email for audit trail without storing PII."""
    import hashlib

    return hashlib.sha256(email.encode()).hexdigest()[:16]
