"""PII export, deletion, and audit-log endpoints (GDPR-ready).

Blueprint: pii_bp  —  url_prefix ``/pii``
"""

from datetime import datetime
from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from ..extensions import db, redis_client
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
    SavingsGoal,
    SavingsContribution,
)
from ..services.cache import cache_delete_patterns
import json
import logging

bp = Blueprint("pii", __name__)
logger = logging.getLogger("finmind.pii")

# ── helpers ──────────────────────────────────────────────────────────

_CONFIRMATION_PHRASE = "DELETE_MY_DATA"


def _log_audit(user_id: int, action: str) -> AuditLog:
    """Write an audit-log row and flush so it survives even if we
    delete the user moments later (we commit in the caller)."""
    entry = AuditLog(user_id=user_id, action=action)
    db.session.add(entry)
    return entry


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "preferred_currency": u.preferred_currency,
        "role": u.role,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _category_to_dict(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _expense_to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "category_id": e.category_id,
        "amount": float(e.amount),
        "currency": e.currency,
        "expense_type": e.expense_type,
        "notes": e.notes or "",
        "spent_at": e.spent_at.isoformat() if e.spent_at else None,
        "source_recurring_id": e.source_recurring_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _recurring_to_dict(r: RecurringExpense) -> dict:
    return {
        "id": r.id,
        "category_id": r.category_id,
        "amount": float(r.amount),
        "currency": r.currency,
        "expense_type": r.expense_type,
        "notes": r.notes,
        "cadence": r.cadence.value if r.cadence else None,
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "active": r.active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _bill_to_dict(b: Bill) -> dict:
    return {
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
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def _reminder_to_dict(r: Reminder) -> dict:
    return {
        "id": r.id,
        "bill_id": r.bill_id,
        "message": r.message,
        "send_at": r.send_at.isoformat() if r.send_at else None,
        "sent": r.sent,
        "channel": r.channel,
    }


def _subscription_to_dict(s: UserSubscription) -> dict:
    return {
        "id": s.id,
        "plan_id": s.plan_id,
        "active": s.active,
        "started_at": s.started_at.isoformat() if s.started_at else None,
    }


def _savings_goal_to_dict(g: SavingsGoal) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "color": g.color,
        "icon": g.icon,
        "completed": g.completed,
        "completed_at": g.completed_at.isoformat() if g.completed_at else None,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _savings_contribution_to_dict(c: SavingsContribution) -> dict:
    return {
        "id": c.id,
        "goal_id": c.goal_id,
        "amount": float(c.amount),
        "notes": c.notes,
        "contributed_at": c.contributed_at.isoformat() if c.contributed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _audit_to_dict(a: AuditLog) -> dict:
    return {
        "id": a.id,
        "action": a.action,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ── routes ───────────────────────────────────────────────────────────


@bp.get("/export")
@jwt_required()
def export_data():
    """Return ALL personal data as a downloadable JSON file."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": _user_to_dict(user),
        "categories": [
            _category_to_dict(c)
            for c in db.session.query(Category)
            .filter_by(user_id=uid)
            .order_by(Category.id)
            .all()
        ],
        "expenses": [
            _expense_to_dict(e)
            for e in db.session.query(Expense)
            .filter_by(user_id=uid)
            .order_by(Expense.id)
            .all()
        ],
        "recurring_expenses": [
            _recurring_to_dict(r)
            for r in db.session.query(RecurringExpense)
            .filter_by(user_id=uid)
            .order_by(RecurringExpense.id)
            .all()
        ],
        "bills": [
            _bill_to_dict(b)
            for b in db.session.query(Bill)
            .filter_by(user_id=uid)
            .order_by(Bill.id)
            .all()
        ],
        "reminders": [
            _reminder_to_dict(r)
            for r in db.session.query(Reminder)
            .filter_by(user_id=uid)
            .order_by(Reminder.id)
            .all()
        ],
        "subscriptions": [
            _subscription_to_dict(s)
            for s in db.session.query(UserSubscription)
            .filter_by(user_id=uid)
            .order_by(UserSubscription.id)
            .all()
        ],
        "savings_goals": [
            _savings_goal_to_dict(g)
            for g in db.session.query(SavingsGoal)
            .filter_by(user_id=uid)
            .order_by(SavingsGoal.id)
            .all()
        ],
        "audit_log": [
            _audit_to_dict(a)
            for a in db.session.query(AuditLog)
            .filter_by(user_id=uid)
            .order_by(AuditLog.id)
            .all()
        ],
    }

    _log_audit(uid, "PII_EXPORT")
    db.session.commit()

    body = json.dumps(payload, indent=2, ensure_ascii=False)
    logger.info("PII export user=%s size=%s", uid, len(body))

    return Response(
        body,
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="finmind-data-export-{uid}.json"'
        },
    )


@bp.post("/delete")
@jwt_required()
def delete_data():
    """Permanently delete ALL user data.  Requires ``{"confirm": "DELETE_MY_DATA"}``."""
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    if data.get("confirm") != _CONFIRMATION_PHRASE:
        return jsonify(
            error=f'confirmation required: send {{"confirm": "{_CONFIRMATION_PHRASE}"}}'
        ), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    # Audit BEFORE deletion (user_id set to NULL after user row is gone,
    # but we keep the log entry with user_id while we still can).
    _log_audit(uid, "PII_DELETE")
    db.session.flush()  # ensure audit row is written

    # Delete in dependency order (children first) to avoid FK violations.
    db.session.query(AdImpression).filter_by(user_id=uid).delete()
    db.session.query(UserSubscription).filter_by(user_id=uid).delete()
    # Reminders may reference bills, delete reminders first.
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    # Expenses may reference recurring_expenses; delete expenses first.
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()
    # Savings contributions cascade from goals, but be explicit.
    goal_ids = [
        g.id
        for g in db.session.query(SavingsGoal.id).filter_by(user_id=uid).all()
    ]
    if goal_ids:
        db.session.query(SavingsContribution).filter(
            SavingsContribution.goal_id.in_(goal_ids)
        ).delete(synchronize_session="fetch")
    db.session.query(SavingsGoal).filter_by(user_id=uid).delete()

    # Nullify user_id on audit_logs so FK constraint is satisfied but
    # we retain the audit trail.
    db.session.query(AuditLog).filter_by(user_id=uid).update({"user_id": None})

    # Finally remove the user row itself.
    db.session.delete(user)
    db.session.commit()

    logger.info("PII delete completed user=%s", uid)

    # Best-effort: revoke current JWT by adding its jti to a Redis blocklist.
    try:
        claims = get_jwt()
        jti = claims.get("jti")
        if jti:
            redis_client.setex(f"jwt:blocklist:{jti}", 3600, "revoked")
    except Exception:
        pass  # Redis unavailability must not block the delete response.

    # Invalidate all cached data for this user.
    cache_delete_patterns(
        [
            f"user:{uid}:*",
            f"insights:{uid}:*",
        ]
    )

    return jsonify(message="All personal data has been permanently deleted."), 200


@bp.get("/audit-log")
@jwt_required()
def audit_log():
    """Return audit-log entries for the authenticated user."""
    uid = int(get_jwt_identity())
    entries = (
        db.session.query(AuditLog)
        .filter_by(user_id=uid)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    _log_audit(uid, "PII_AUDIT_LOG_VIEW")
    db.session.commit()

    logger.info("PII audit-log view user=%s count=%s", uid, len(entries))
    return jsonify([_audit_to_dict(a) for a in entries])
