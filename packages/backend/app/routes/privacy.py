from decimal import Decimal
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import (
    AuditLog,
    Bill,
    Category,
    Expense,
    Reminder,
    RecurringExpense,
    User,
    UserSubscription,
)

bp = Blueprint("privacy", __name__)


@bp.get("/export")
@jwt_required()
def export_personal_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    package = _build_export_package(user)
    db.session.add(AuditLog(user_id=user.id, action="PII_EXPORT"))
    db.session.commit()
    return jsonify(package)


@bp.post("/delete")
@jwt_required()
def delete_personal_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    password = data.get("password")
    if not password:
        return jsonify(error="password required"), 400
    if not check_password_hash(user.password_hash, password):
        return jsonify(error="invalid password"), 403

    _delete_user_records(user.id)
    db.session.add(AuditLog(user_id=None, action=f"PII_DELETE:user:{user.id}"))
    db.session.delete(user)
    db.session.commit()
    return jsonify(message="personal data deleted"), 200


def _build_export_package(user: User) -> dict:
    user_id = user.id
    return {
        "generated_at": _serialize(datetime.utcnow()),
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": _serialize(user.created_at),
        },
        "categories": _serialize_rows(
            db.session.query(Category).filter_by(user_id=user_id).all()
        ),
        "expenses": _serialize_rows(
            db.session.query(Expense).filter_by(user_id=user_id).all()
        ),
        "recurring_expenses": _serialize_rows(
            db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
        ),
        "bills": _serialize_rows(
            db.session.query(Bill).filter_by(user_id=user_id).all()
        ),
        "reminders": _serialize_rows(
            db.session.query(Reminder).filter_by(user_id=user_id).all()
        ),
        "subscriptions": _serialize_rows(
            db.session.query(UserSubscription).filter_by(user_id=user_id).all()
        ),
        "audit_logs": _serialize_rows(
            db.session.query(AuditLog).filter_by(user_id=user_id).all()
        ),
    }


def _delete_user_records(user_id: int) -> None:
    models = [
        Reminder,
        Bill,
        Expense,
        RecurringExpense,
        Category,
        UserSubscription,
    ]
    for model in models:
        db.session.query(model).filter_by(user_id=user_id).delete(
            synchronize_session=False
        )
    db.session.query(AuditLog).filter_by(user_id=user_id).update(
        {"user_id": None}, synchronize_session=False
    )


def _serialize_rows(rows: list[db.Model]) -> list[dict]:
    return [_serialize_row(row) for row in rows]


def _serialize_row(row: db.Model) -> dict:
    return {
        column.name: _serialize(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
