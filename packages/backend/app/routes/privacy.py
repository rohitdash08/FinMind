from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
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
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")

DELETION_GRACE_DAYS = 30


def _log_audit(user_id, action, detail=None):
    """Record a GDPR audit event with request metadata."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        detail=detail,
        ip_address=request.remote_addr,
        user_agent=(request.user_agent.string or "")[:500],
    )
    db.session.add(entry)
    db.session.flush()


@bp.get("/export")
@jwt_required()
def export_data():
    """Export all PII associated with the authenticated user as JSON."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
        "deletion_requested_at": (
            user.deletion_requested_at.isoformat()
            if user.deletion_requested_at
            else None
        ),
    }

    expenses = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in db.session.query(Expense).filter_by(user_id=uid).all()
    ]

    recurring = [
        {
            "id": r.id,
            "amount": float(r.amount),
            "currency": r.currency,
            "expense_type": r.expense_type,
            "notes": r.notes,
            "cadence": r.cadence.value,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "active": r.active,
        }
        for r in db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    ]

    categories = [
        {"id": c.id, "name": c.name}
        for c in db.session.query(Category).filter_by(user_id=uid).all()
    ]

    bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay_enabled": b.autopay_enabled,
            "active": b.active,
        }
        for b in db.session.query(Bill).filter_by(user_id=uid).all()
    ]

    reminders = [
        {
            "id": r.id,
            "bill_id": r.bill_id,
            "message": r.message,
            "send_at": r.send_at.isoformat(),
            "sent": r.sent,
            "channel": r.channel,
        }
        for r in db.session.query(Reminder).filter_by(user_id=uid).all()
    ]

    subscriptions = [
        {
            "id": s.id,
            "plan_id": s.plan_id,
            "active": s.active,
            "started_at": s.started_at.isoformat(),
        }
        for s in db.session.query(UserSubscription).filter_by(user_id=uid).all()
    ]

    _log_audit(uid, "pii_export")
    db.session.commit()

    logger.info("PII export generated for user_id=%s", uid)
    return jsonify(
        profile=profile,
        expenses=expenses,
        recurring_expenses=recurring,
        categories=categories,
        bills=bills,
        reminders=reminders,
        subscriptions=subscriptions,
        exported_at=datetime.utcnow().isoformat(),
    )


@bp.post("/delete-request")
@jwt_required()
def request_deletion():
    """Initiate account deletion with a 30-day grace period."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    if user.deletion_requested_at:
        return (
            jsonify(
                error="deletion already requested",
                deletion_scheduled_for=user.deletion_scheduled_for.isoformat(),
            ),
            409,
        )

    now = datetime.utcnow()
    scheduled = now + timedelta(days=DELETION_GRACE_DAYS)
    user.deletion_requested_at = now
    user.deletion_scheduled_for = scheduled

    _log_audit(uid, "deletion_requested", f"scheduled_for={scheduled.isoformat()}")
    db.session.commit()

    logger.info("Deletion requested for user_id=%s scheduled=%s", uid, scheduled)
    return jsonify(
        message="deletion scheduled",
        deletion_requested_at=now.isoformat(),
        deletion_scheduled_for=scheduled.isoformat(),
        grace_period_days=DELETION_GRACE_DAYS,
    )


@bp.post("/delete-cancel")
@jwt_required()
def cancel_deletion():
    """Cancel a pending deletion request during the grace period."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    if not user.deletion_requested_at:
        return jsonify(error="no pending deletion request"), 400

    user.deletion_requested_at = None
    user.deletion_scheduled_for = None

    _log_audit(uid, "deletion_cancelled")
    db.session.commit()

    logger.info("Deletion cancelled for user_id=%s", uid)
    return jsonify(message="deletion cancelled")


@bp.post("/delete-confirm")
@jwt_required()
def confirm_deletion():
    """Permanently delete all user data. Requires an active deletion request."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    if not user.deletion_requested_at:
        return jsonify(error="no pending deletion request"), 400

    # Record audit BEFORE deleting (audit logs are retained with user_id=NULL)
    _log_audit(uid, "deletion_confirmed", f"email={user.email}")

    # Cascade delete all user data
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()
    db.session.query(UserSubscription).filter_by(user_id=uid).delete()
    db.session.query(AdImpression).filter_by(user_id=uid).delete()

    # Nullify user references in audit logs (retain for compliance)
    db.session.query(AuditLog).filter_by(user_id=uid).update({"user_id": None})

    db.session.delete(user)
    db.session.commit()

    logger.info("User permanently deleted user_id=%s", uid)
    return jsonify(message="account permanently deleted")


@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    """Return the authenticated user's GDPR audit trail."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    logs = (
        db.session.query(AuditLog)
        .filter_by(user_id=uid)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        [
            {
                "id": log.id,
                "action": log.action,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    )


@bp.get("/deletion-status")
@jwt_required()
def deletion_status():
    """Check whether a deletion request is pending."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    if not user.deletion_requested_at:
        return jsonify(pending=False)

    return jsonify(
        pending=True,
        deletion_requested_at=user.deletion_requested_at.isoformat(),
        deletion_scheduled_for=user.deletion_scheduled_for.isoformat(),
    )
