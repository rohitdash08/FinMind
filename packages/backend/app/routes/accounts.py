from datetime import date
from decimal import Decimal, InvalidOperation
from sqlalchemy import extract, func

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Account, AccountType, Expense, User
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Account)
        .filter_by(user_id=uid, is_active=True)
        .order_by(Account.created_at.desc())
        .all()
    )
    logger.info("List accounts user=%s count=%s", uid, len(items))
    return jsonify([_account_to_dict(a) for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = str(data.get("account_type") or "CHECKING").upper()
    if account_type not in {t.value for t in AccountType}:
        return jsonify(error="invalid account_type"), 400
    balance = _parse_amount(data.get("balance")) or Decimal("0")
    account = Account(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        balance=balance,
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", account.id, uid, name)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    today = date.today()
    expense_count = (
        db.session.query(func.count(Expense.id))
        .filter(Expense.user_id == uid, Expense.account_id == account_id)
        .scalar()
    )
    month_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == account_id,
            Expense.expense_type != "INCOME",
            extract("year", Expense.spent_at) == today.year,
            extract("month", Expense.spent_at) == today.month,
        )
        .scalar()
    )
    month_income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == account_id,
            Expense.expense_type == "INCOME",
            extract("year", Expense.spent_at) == today.year,
            extract("month", Expense.spent_at) == today.month,
        )
        .scalar()
    )
    d = _account_to_dict(account)
    d["expense_count"] = expense_count or 0
    d["month_expenses"] = float(month_expenses or 0)
    d["month_income"] = float(month_income or 0)
    return jsonify(d)


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account_type = str(data.get("account_type") or "").upper()
        if account_type not in {t.value for t in AccountType}:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "currency" in data:
        account.currency = str(data.get("currency") or "INR")[:10]
    if "balance" in data:
        balance = _parse_amount(data.get("balance"))
        if balance is not None:
            account.balance = balance
    if "is_active" in data:
        account.is_active = bool(data.get("is_active"))
    db.session.commit()
    logger.info("Updated account id=%s user=%s", account.id, uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(account)
    db.session.commit()
    logger.info("Deleted account id=%s user=%s", account_id, uid)
    return jsonify(message="deleted")


def _account_to_dict(a: Account) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
