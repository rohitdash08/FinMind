import hashlib
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

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
from ..services.cache import cache_delete_patterns

bp = Blueprint("privacy", __name__)


@bp.get("/export")
@jwt_required()
def export_personal_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    _write_audit_log(uid, "privacy.export_requested")
    db.session.commit()

    return jsonify(
        generated_at=datetime.now(timezone.utc).isoformat(),
        user=_user_to_dict(user),
        categories=[_category_to_dict(row) for row in _for_user(Category, uid)],
        expenses=[_expense_to_dict(row) for row in _for_user(Expense, uid)],
        recurring_expenses=[
            _recurring_expense_to_dict(row) for row in _for_user(RecurringExpense, uid)
        ],
        bills=[_bill_to_dict(row) for row in _for_user(Bill, uid)],
        reminders=[_reminder_to_dict(row) for row in _for_user(Reminder, uid)],
        subscriptions=[_subscription_to_dict(row) for row in _for_user(UserSubscription, uid)],
        ad_impressions=[_ad_impression_to_dict(row) for row in _for_user(AdImpression, uid)],
        audit_logs=[_audit_log_to_dict(row) for row in _for_user(AuditLog, uid)],
    )


@bp.delete("/delete")
@jwt_required()
def delete_personal_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    if data.get("confirmation") != "DELETE":
        return jsonify(error='confirmation must equal "DELETE"'), 400

    email_hash = hashlib.sha256(user.email.encode("utf-8")).hexdigest()

    for model in (
        Reminder,
        Bill,
        Expense,
        RecurringExpense,
        Category,
        UserSubscription,
        AdImpression,
    ):
        db.session.query(model).filter_by(user_id=uid).delete(synchronize_session=False)

    db.session.query(AuditLog).filter_by(user_id=uid).update(
        {"user_id": None}, synchronize_session=False
    )
    db.session.delete(user)
    db.session.add(
        AuditLog(
            user_id=None,
            action=f"privacy.delete_completed:{email_hash}",
        )
    )
    db.session.commit()

    cache_delete_patterns([f"user:{uid}:*", f"insights:{uid}:*"])
    return jsonify(message="personal data permanently deleted"), 200


def _for_user(model, uid: int):
    return db.session.query(model).filter_by(user_id=uid).all()


def _write_audit_log(uid: int, action: str) -> None:
    db.session.add(AuditLog(user_id=uid, action=action))


def _iso(value):
    return value.isoformat() if value else None


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": _iso(user.created_at),
    }


def _category_to_dict(row: Category) -> dict:
    return {"id": row.id, "name": row.name, "created_at": _iso(row.created_at)}


def _expense_to_dict(row: Expense) -> dict:
    return {
        "id": row.id,
        "category_id": row.category_id,
        "amount": float(row.amount),
        "currency": row.currency,
        "expense_type": row.expense_type,
        "description": row.notes or "",
        "spent_at": _iso(row.spent_at),
        "source_recurring_id": row.source_recurring_id,
        "created_at": _iso(row.created_at),
    }


def _recurring_expense_to_dict(row: RecurringExpense) -> dict:
    return {
        "id": row.id,
        "category_id": row.category_id,
        "amount": float(row.amount),
        "currency": row.currency,
        "expense_type": row.expense_type,
        "description": row.notes,
        "cadence": row.cadence.value,
        "start_date": _iso(row.start_date),
        "end_date": _iso(row.end_date),
        "active": row.active,
        "created_at": _iso(row.created_at),
    }


def _bill_to_dict(row: Bill) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "amount": float(row.amount),
        "currency": row.currency,
        "next_due_date": _iso(row.next_due_date),
        "cadence": row.cadence.value,
        "autopay_enabled": row.autopay_enabled,
        "channel_whatsapp": row.channel_whatsapp,
        "channel_email": row.channel_email,
        "active": row.active,
        "created_at": _iso(row.created_at),
    }


def _reminder_to_dict(row: Reminder) -> dict:
    return {
        "id": row.id,
        "bill_id": row.bill_id,
        "message": row.message,
        "send_at": _iso(row.send_at),
        "sent": row.sent,
        "channel": row.channel,
    }


def _subscription_to_dict(row: UserSubscription) -> dict:
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "active": row.active,
        "started_at": _iso(row.started_at),
    }


def _ad_impression_to_dict(row: AdImpression) -> dict:
    return {"id": row.id, "placement": row.placement, "created_at": _iso(row.created_at)}


def _audit_log_to_dict(row: AuditLog) -> dict:
    return {"id": row.id, "action": row.action, "created_at": _iso(row.created_at)}
