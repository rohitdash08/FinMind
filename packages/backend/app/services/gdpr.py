"""GDPR-compliant data export and deletion service."""

import json
import hashlib
import secrets
from datetime import datetime, timedelta

from ..extensions import db
from ..models import (
    AdImpression,
    AuditLog,
    Bill,
    Category,
    DataRequest,
    DataRequestStatus,
    DataRequestType,
    Expense,
    RecurringExpense,
    Reminder,
    User,
    UserSubscription,
)
import logging

logger = logging.getLogger("finmind.gdpr")

# Export download URLs expire after 24 hours
EXPORT_EXPIRY_HOURS = 24
EXPORT_SCHEMA_VERSION = "1.0.0"


def request_data_export(user_id: int) -> DataRequest:
    """Create an export request and immediately generate the export package."""
    req = DataRequest(
        user_id=user_id,
        request_type=DataRequestType.EXPORT.value,
        status=DataRequestStatus.PROCESSING.value,
    )
    db.session.add(req)
    db.session.commit()

    _log_audit(user_id, "GDPR_EXPORT_REQUESTED", f"request_id={req.id}")

    try:
        export_data = generate_export_package(user_id)
        export_json = json.dumps(export_data, ensure_ascii=False, default=str)
        # Generate a unique token for the download
        token = secrets.token_urlsafe(32)
        req.download_url = token
        req.status = DataRequestStatus.COMPLETED.value
        req.completed_at = datetime.utcnow()
        req.expires_at = datetime.utcnow() + timedelta(hours=EXPORT_EXPIRY_HOURS)

        _log_audit(
            user_id,
            "GDPR_EXPORT_GENERATED",
            json.dumps({"request_id": req.id, "token": token, "size_bytes": len(export_json)}),
        )

        db.session.commit()
        logger.info("Export generated for user_id=%s request_id=%s", user_id, req.id)
        return req
    except Exception as exc:
        req.status = DataRequestStatus.FAILED.value
        req.completed_at = datetime.utcnow()
        db.session.commit()
        _log_audit(user_id, "GDPR_EXPORT_FAILED", str(exc))
        logger.exception("Export failed for user_id=%s", user_id)
        raise


def generate_export_package(user_id: int) -> dict:
    """Collect ALL user data and return as structured dictionary."""
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    # Profile
    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }

    # Categories
    categories = [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in db.session.query(Category).filter_by(user_id=user_id).all()
    ]

    # Expenses
    expenses = [
        {
            "id": e.id,
            "amount": str(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "category_id": e.category_id,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat() if e.spent_at else None,
            "source_recurring_id": e.source_recurring_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in db.session.query(Expense).filter_by(user_id=user_id).all()
    ]

    # Recurring expenses
    recurring_expenses = [
        {
            "id": r.id,
            "amount": str(r.amount),
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
        for r in db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    ]

    # Bills
    bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": str(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
            "cadence": b.cadence.value if b.cadence else None,
            "autopay_enabled": b.autopay_enabled,
            "channel_whatsapp": b.channel_whatsapp,
            "channel_email": b.channel_email,
            "active": b.active,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in db.session.query(Bill).filter_by(user_id=user_id).all()
    ]

    # Reminders
    reminders = [
        {
            "id": rm.id,
            "bill_id": rm.bill_id,
            "message": rm.message,
            "send_at": rm.send_at.isoformat() if rm.send_at else None,
            "sent": rm.sent,
            "channel": rm.channel,
        }
        for rm in db.session.query(Reminder).filter_by(user_id=user_id).all()
    ]

    # Subscriptions
    subscriptions = [
        {
            "id": s.id,
            "plan_id": s.plan_id,
            "active": s.active,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in db.session.query(UserSubscription).filter_by(user_id=user_id).all()
    ]

    # Ad impressions
    ad_impressions = [
        {
            "id": ai.id,
            "placement": ai.placement,
            "created_at": ai.created_at.isoformat() if ai.created_at else None,
        }
        for ai in db.session.query(AdImpression).filter_by(user_id=user_id).all()
    ]

    # Audit logs (user's own actions)
    audit_logs = [
        {
            "id": al.id,
            "action": al.action,
            "details": al.details,
            "created_at": al.created_at.isoformat() if al.created_at else None,
        }
        for al in db.session.query(AuditLog).filter_by(user_id=user_id).all()
    ]

    return {
        "metadata": {
            "export_date": datetime.utcnow().isoformat(),
            "schema_version": EXPORT_SCHEMA_VERSION,
            "user_id": user_id,
        },
        "profile": profile,
        "categories": categories,
        "expenses": expenses,
        "recurring_expenses": recurring_expenses,
        "bills": bills,
        "reminders": reminders,
        "subscriptions": subscriptions,
        "ad_impressions": ad_impressions,
        "audit_logs": audit_logs,
    }


def generate_deletion_token(user_id: int) -> str:
    """Generate a time-limited token for confirming account deletion."""
    token = secrets.token_urlsafe(32)
    _log_audit(
        user_id,
        "GDPR_DELETE_TOKEN_ISSUED",
        json.dumps({"token": token, "expires_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat()}),
    )
    return token


def request_data_deletion(user_id: int) -> dict:
    """Create a deletion request. Returns a confirmation token that must be
    sent back to ``confirm_data_deletion`` to actually execute the deletion."""
    req = DataRequest(
        user_id=user_id,
        request_type=DataRequestType.DELETE.value,
        status=DataRequestStatus.PENDING.value,
    )
    db.session.add(req)
    db.session.commit()

    token = generate_deletion_token(user_id)
    _log_audit(user_id, "GDPR_DELETE_REQUESTED", f"request_id={req.id}")

    logger.info("Deletion requested for user_id=%s request_id=%s", user_id, req.id)
    return {"request_id": req.id, "confirmation_token": token}


def confirm_data_deletion(user_id: int, request_id: int, confirmation_token: str) -> DataRequest:
    """Verify the confirmation token and execute the deletion."""
    req = db.session.get(DataRequest, request_id)
    if not req or req.user_id != user_id:
        raise ValueError("Request not found")
    if req.request_type != DataRequestType.DELETE.value:
        raise ValueError("Not a deletion request")
    if req.status != DataRequestStatus.PENDING.value:
        raise ValueError("Request already processed")

    # Verify token by checking audit log
    token_log = (
        db.session.query(AuditLog)
        .filter_by(user_id=user_id, action="GDPR_DELETE_TOKEN_ISSUED")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if not token_log or not token_log.details:
        raise ValueError("Invalid confirmation token")

    token_data = json.loads(token_log.details)
    if token_data.get("token") != confirmation_token:
        raise ValueError("Invalid confirmation token")

    expires_at = datetime.fromisoformat(token_data["expires_at"])
    if datetime.utcnow() > expires_at:
        raise ValueError("Confirmation token expired")

    # Execute deletion
    req.status = DataRequestStatus.PROCESSING.value
    db.session.commit()

    try:
        execute_data_deletion(user_id, req.id)
        req.status = DataRequestStatus.COMPLETED.value
        req.completed_at = datetime.utcnow()
        db.session.commit()
        logger.info("Deletion completed for user_id=%s request_id=%s", user_id, req.id)
        return req
    except Exception as exc:
        req.status = DataRequestStatus.FAILED.value
        req.completed_at = datetime.utcnow()
        db.session.commit()
        logger.exception("Deletion failed for user_id=%s", user_id)
        raise


def execute_data_deletion(user_id: int, request_id: int) -> None:
    """Perform cascade deletion of all user data."""
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    email_hash = hashlib.sha256(user.email.encode()).hexdigest()[:16]

    # Delete in dependency order (children first)
    # Reminders (may reference bills)
    db.session.query(Reminder).filter_by(user_id=user_id).delete()

    # Bills
    db.session.query(Bill).filter_by(user_id=user_id).delete()

    # Expenses (including recurring source references)
    db.session.query(Expense).filter_by(user_id=user_id).delete()

    # Recurring expenses
    db.session.query(RecurringExpense).filter_by(user_id=user_id).delete()

    # Categories
    db.session.query(Category).filter_by(user_id=user_id).delete()

    # Subscriptions
    db.session.query(UserSubscription).filter_by(user_id=user_id).delete()

    # Ad impressions (set user_id to null to preserve analytics)
    db.session.query(AdImpression).filter_by(user_id=user_id).update({"user_id": None})

    # Data requests (keep for audit, remove download URLs)
    db.session.query(DataRequest).filter_by(user_id=user_id).update(
        {"download_url": None}
    )

    # Anonymize audit logs (keep for compliance, remove PII)
    db.session.query(AuditLog).filter_by(user_id=user_id).update(
        {"details": None}
    )

    # Delete the user account
    db.session.delete(user)

    # Create anonymized audit trail entry (with null user_id since user is deleted)
    audit = AuditLog(
        user_id=None,
        action="GDPR_ACCOUNT_DELETED",
        details=json.dumps({
            "request_id": request_id,
            "email_hash": email_hash,
            "deleted_at": datetime.utcnow().isoformat(),
        }),
    )
    db.session.add(audit)
    db.session.flush()

    logger.info(
        "User data deleted: email_hash=%s request_id=%s",
        email_hash, request_id,
    )


def get_request_status(request_id: int, user_id: int) -> dict | None:
    """Check the status of a specific data request."""
    req = db.session.get(DataRequest, request_id)
    if not req or req.user_id != user_id:
        return None
    return _request_to_dict(req)


def get_user_requests(user_id: int) -> list[dict]:
    """List all past data requests for a user."""
    requests = (
        db.session.query(DataRequest)
        .filter_by(user_id=user_id)
        .order_by(DataRequest.created_at.desc())
        .all()
    )
    return [_request_to_dict(r) for r in requests]


def _request_to_dict(req: DataRequest) -> dict:
    return {
        "id": req.id,
        "request_type": req.request_type,
        "status": req.status,
        "has_download": bool(req.download_url) and req.request_type == DataRequestType.EXPORT.value,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }


def _log_audit(user_id: int, action: str, details: str | None = None) -> None:
    """Helper to create an audit log entry."""
    log = AuditLog(user_id=user_id, action=action, details=details)
    db.session.add(log)
    db.session.commit()
