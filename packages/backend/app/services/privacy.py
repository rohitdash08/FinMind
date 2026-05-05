"""
PII Export & Delete Service (GDPR-ready)
Issue #76: https://github.com/rohitdash08/FinMind/issues/76
"""

import json
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from ..extensions import db
from ..models import (
    User, Expense, RecurringExpense, Bill, Reminder,
    Category, AdImpression, UserSubscription, AuditLog,
    DataRequest, DataRequestStatus, DataRequestType,
)

logger = logging.getLogger("finmind.privacy")

CONFIRMATION_TOKEN_EXPIRY_MINUTES = 30
EXPORT_DOWNLOAD_EXPIRY_HOURS = 48
MAX_PENDING_REQUESTS_PER_USER = 3


class PrivacyServiceError(Exception):
    pass

class RateLimitExceeded(PrivacyServiceError):
    pass

class TokenExpired(PrivacyServiceError):
    pass

class TokenInvalid(PrivacyServiceError):
    pass


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:16]

def _audit(user_id: Optional[int], action: str) -> None:
    entry = AuditLog(user_id=user_id, action=action)
    db.session.add(entry)


def request_export(user_id: int) -> "DataRequest":
    pending = DataRequest.query.filter_by(
        user_id=user_id,
        request_type=DataRequestType.EXPORT.value,
        status=DataRequestStatus.COMPLETED.value,
    ).filter(
        DataRequest.created_at > datetime.utcnow() - timedelta(hours=EXPORT_DOWNLOAD_EXPIRY_HOURS)
    ).count()

    if pending >= MAX_PENDING_REQUESTS_PER_USER:
        raise RateLimitExceeded(
            f"Maximum {MAX_PENDING_REQUESTS_PER_USER} active exports allowed."
        )

    dr = DataRequest(
        user_id=user_id,
        request_type=DataRequestType.EXPORT.value,
        status=DataRequestStatus.PROCESSING.value,
    )
    db.session.add(dr)
    db.session.flush()

    package = _collect_user_data(user_id)
    dr.package_path = json.dumps(package)
    dr.status = DataRequestStatus.COMPLETED.value
    dr.completed_at = datetime.utcnow()
    dr.metadata_json = json.dumps({
        "record_counts": {k: len(v) if isinstance(v, list) else 1 for k, v in package.items()},
        "generated_at": datetime.utcnow().isoformat(),
        "format_version": "1.0",
    })

    _audit(user_id, "pii_export_completed")
    db.session.commit()
    logger.info("Export completed for user_id=%s request_id=%s", user_id, dr.id)
    return dr


def _collect_user_data(user_id: int) -> dict:
    user = db.session.get(User, user_id)
    if not user:
        raise PrivacyServiceError("User not found")

    def ser(d):
        if d is None:
            return None
        if hasattr(d, 'isoformat'):
            return d.isoformat()
        return str(d)

    profile = {
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": ser(user.created_at),
    }
    categories = [
        {"id": c.id, "name": c.name, "created_at": ser(c.created_at)}
        for c in Category.query.filter_by(user_id=user_id).all()
    ]
    expenses = [
        {"id": e.id, "amount": str(e.amount), "currency": e.currency,
         "expense_type": e.expense_type, "notes": e.notes,
         "spent_at": ser(e.spent_at), "category_id": e.category_id,
         "created_at": ser(e.created_at)}
        for e in Expense.query.filter_by(user_id=user_id).all()
    ]
    recurring = [
        {"id": r.id, "amount": str(r.amount), "currency": r.currency,
         "expense_type": r.expense_type, "notes": r.notes,
         "cadence": r.cadence.value if r.cadence else None,
         "start_date": ser(r.start_date), "end_date": ser(r.end_date),
         "active": r.active, "created_at": ser(r.created_at)}
        for r in RecurringExpense.query.filter_by(user_id=user_id).all()
    ]
    bills = [
        {"id": b.id, "name": b.name, "amount": str(b.amount),
         "currency": b.currency, "next_due_date": ser(b.next_due_date),
         "cadence": b.cadence.value if b.cadence else None,
         "autopay_enabled": b.autopay_enabled, "active": b.active,
         "created_at": ser(b.created_at)}
        for b in Bill.query.filter_by(user_id=user_id).all()
    ]
    reminders = [
        {"id": rem.id, "message": rem.message, "send_at": ser(rem.send_at),
         "sent": rem.sent, "channel": rem.channel, "bill_id": rem.bill_id}
        for rem in Reminder.query.filter_by(user_id=user_id).all()
    ]
    subscriptions = [
        {"id": s.id, "plan_id": s.plan_id, "active": s.active, "started_at": ser(s.started_at)}
        for s in UserSubscription.query.filter_by(user_id=user_id).all()
    ]
    audit_logs = [
        {"id": a.id, "action": a.action, "created_at": ser(a.created_at)}
        for a in AuditLog.query.filter_by(user_id=user_id).all()
    ]

    return {
        "export_metadata": {
            "format": "FinMind GDPR Export v1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
        },
        "profile": profile,
        "categories": categories,
        "expenses": expenses,
        "recurring_expenses": recurring,
        "bills": bills,
        "reminders": reminders,
        "subscriptions": subscriptions,
        "audit_logs": audit_logs,
    }


def get_export_package(request_id: int, user_id: int) -> Optional[dict]:
    dr = DataRequest.query.filter_by(
        id=request_id, user_id=user_id,
        request_type=DataRequestType.EXPORT.value,
        status=DataRequestStatus.COMPLETED.value,
    ).first()
    if not dr:
        return None
    if dr.completed_at and (datetime.utcnow() - dr.completed_at).total_seconds() > EXPORT_DOWNLOAD_EXPIRY_HOURS * 3600:
        dr.status = DataRequestStatus.EXPIRED.value
        db.session.commit()
        return None
    _audit(user_id, f"pii_export_downloaded request_id={request_id}")
    db.session.commit()
    return json.loads(dr.package_path)


def request_deletion(user_id: int) -> "DataRequest":
    existing = DataRequest.query.filter_by(
        user_id=user_id,
        request_type=DataRequestType.DELETE.value,
        status=DataRequestStatus.PENDING.value,
    ).first()
    if existing:
        existing.status = DataRequestStatus.EXPIRED.value

    token = secrets.token_urlsafe(32)
    dr = DataRequest(
        user_id=user_id,
        request_type=DataRequestType.DELETE.value,
        status=DataRequestStatus.PENDING.value,
        confirmation_token=token,
        token_expires_at=datetime.utcnow() + timedelta(minutes=CONFIRMATION_TOKEN_EXPIRY_MINUTES),
    )
    db.session.add(dr)
    _audit(user_id, "pii_deletion_requested")
    db.session.commit()
    logger.info("Deletion requested for user_id=%s request_id=%s", user_id, dr.id)
    return dr


def confirm_deletion(user_id: int, token: str) -> "DataRequest":
    dr = DataRequest.query.filter_by(
        user_id=user_id,
        request_type=DataRequestType.DELETE.value,
        status=DataRequestStatus.PENDING.value,
        confirmation_token=token,
    ).first()
    if not dr:
        raise TokenInvalid("Invalid or already used confirmation token.")
    if datetime.utcnow() > dr.token_expires_at:
        dr.status = DataRequestStatus.EXPIRED.value
        db.session.commit()
        raise TokenExpired("Confirmation token has expired. Please request deletion again.")

    dr.status = DataRequestStatus.PROCESSING.value
    db.session.flush()

    user = db.session.get(User, user_id)
    if not user:
        raise PrivacyServiceError("User not found")

    email_hash = _hash_email(user.email)
    deletion_counts = {}

    # FK-safe deletion order
    deletion_counts["reminders"] = Reminder.query.filter_by(user_id=user_id).delete()
    deletion_counts["expenses"] = Expense.query.filter_by(user_id=user_id).delete()
    deletion_counts["recurring_expenses"] = RecurringExpense.query.filter_by(user_id=user_id).delete()
    deletion_counts["bills"] = Bill.query.filter_by(user_id=user_id).delete()
    deletion_counts["categories"] = Category.query.filter_by(user_id=user_id).delete()
    deletion_counts["ad_impressions_anonymized"] = AdImpression.query.filter_by(user_id=user_id).update({"user_id": None})
    deletion_counts["subscriptions"] = UserSubscription.query.filter_by(user_id=user_id).delete()

    # Anonymize audit logs
    audit_entries = AuditLog.query.filter_by(user_id=user_id).all()
    for entry in audit_entries:
        entry.user_id = None
        entry.action = f"[deleted_user:{email_hash}] {entry.action}"
    deletion_counts["audit_logs_anonymized"] = len(audit_entries)

    # Finalize request record
    dr.status = DataRequestStatus.COMPLETED.value
    dr.completed_at = datetime.utcnow()
    dr.user_id = None
    dr.confirmation_token = None
    dr.metadata_json = json.dumps({
        "email_hash": email_hash,
        "deletion_counts": deletion_counts,
        "completed_at": datetime.utcnow().isoformat(),
    })

    db.session.add(AuditLog(
        user_id=None,
        action=f"[deleted_user:{email_hash}] account_permanently_deleted",
    ))

    db.session.delete(user)
    db.session.commit()
    logger.info("Account deleted: email_hash=%s counts=%s", email_hash, deletion_counts)
    return dr


def get_request_history(user_id: int) -> list:
    requests = DataRequest.query.filter_by(user_id=user_id).order_by(
        DataRequest.created_at.desc()
    ).all()
    return [
        {
            "id": r.id, "type": r.request_type, "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "expires_at": r.token_expires_at.isoformat() if r.token_expires_at else None,
        }
        for r in requests
    ]
