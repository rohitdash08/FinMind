from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, FinancialAccount, User
from ..services.cache import cache_delete_patterns

bp = Blueprint("accounts", __name__)

ACCOUNT_TYPES = {
    "CASH",
    "CHECKING",
    "SAVINGS",
    "CREDIT_CARD",
    "INVESTMENT",
    "LOAN",
    "WALLET",
    "OTHER",
}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_archived = request.args.get("include_archived") == "true"
    query = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_archived:
        query = query.filter(FinancialAccount.active.is_(True))
    accounts = query.order_by(FinancialAccount.name.asc()).all()
    return jsonify(
        [_account_to_dict(account, include_totals=True) for account in accounts]
    )


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = _parse_account_type(data.get("account_type") or data.get("type"))
    if account_type is None:
        return jsonify(error="invalid account_type"), 400
    opening_balance = _parse_amount(data.get("opening_balance", 0))
    if opening_balance is None:
        return jsonify(error="invalid opening_balance"), 400
    exists = (
        db.session.query(FinancialAccount.id).filter_by(user_id=uid, name=name).first()
    )
    if exists:
        return jsonify(error="account already exists"), 409
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        institution=_clean_optional(data.get("institution"), 120),
        last_four=_parse_last_four(data.get("last_four")),
        currency=(data.get("currency") or (user.preferred_currency if user else "INR"))[
            :10
        ],
        opening_balance=opening_balance,
        active=True,
    )
    db.session.add(account)
    db.session.commit()
    _invalidate_account_caches(uid)
    return jsonify(_account_to_dict(account, include_totals=True)), 201


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        exists = (
            db.session.query(FinancialAccount.id)
            .filter(
                FinancialAccount.user_id == uid,
                FinancialAccount.name == name,
                FinancialAccount.id != account.id,
            )
            .first()
        )
        if exists:
            return jsonify(error="account already exists"), 409
        account.name = name
    if "account_type" in data or "type" in data:
        account_type = _parse_account_type(data.get("account_type") or data.get("type"))
        if account_type is None:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "institution" in data:
        account.institution = _clean_optional(data.get("institution"), 120)
    if "last_four" in data:
        account.last_four = _parse_last_four(data.get("last_four"))
    if "currency" in data:
        account.currency = str(data.get("currency") or "INR")[:10]
    if "opening_balance" in data:
        opening_balance = _parse_amount(data.get("opening_balance"))
        if opening_balance is None:
            return jsonify(error="invalid opening_balance"), 400
        account.opening_balance = opening_balance
    if "active" in data:
        account.active = bool(data.get("active"))
    db.session.commit()
    _invalidate_account_caches(uid)
    return jsonify(_account_to_dict(account, include_totals=True))


@bp.delete("/<int:account_id>")
@jwt_required()
def archive_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    account.active = False
    db.session.commit()
    _invalidate_account_caches(uid)
    return jsonify(message="archived")


def account_belongs_to_user(account_id: int | None, uid: int) -> bool:
    if account_id is None:
        return True
    return (
        db.session.query(FinancialAccount.id)
        .filter_by(id=account_id, user_id=uid)
        .first()
        is not None
    )


def _account_to_dict(account: FinancialAccount, include_totals: bool = False) -> dict:
    payload = {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "institution": account.institution,
        "last_four": account.last_four,
        "currency": account.currency,
        "opening_balance": float(account.opening_balance or 0),
        "active": account.active,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
    }
    if include_totals:
        totals = _account_totals(account.id)
        payload.update(totals)
    return payload


def _account_totals(account_id: int) -> dict:
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.account_id == account_id, Expense.expense_type == "INCOME")
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.account_id == account_id, Expense.expense_type != "INCOME")
        .scalar()
    )
    balance = Decimal(str(income or 0)) - Decimal(str(expenses or 0))
    opening = Decimal(
        str(db.session.get(FinancialAccount, account_id).opening_balance or 0)
    )
    return {
        "income_total": float(income or 0),
        "expense_total": float(expenses or 0),
        "balance": float((opening + balance).quantize(Decimal("0.01"))),
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_account_type(raw) -> str | None:
    account_type = str(raw or "CHECKING").upper().strip()
    return account_type if account_type in ACCOUNT_TYPES else None


def _parse_last_four(raw) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return value[-4:]


def _clean_optional(raw, limit: int) -> str | None:
    value = str(raw or "").strip()
    return value[:limit] if value else None


def _invalidate_account_caches(uid: int) -> None:
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
