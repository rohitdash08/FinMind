import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Account, AccountType, Expense, Category
from ..services.cache import (
    cache_delete_patterns,
    cache_get,
    cache_set,
    accounts_key,
    account_summary_key,
    dashboard_overview_key,
)

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    cached = cache_get(accounts_key(uid))
    if cached is not None:
        return jsonify(cached)
    items = (
        db.session.query(Account)
        .filter_by(user_id=uid, is_active=True)
        .order_by(Account.is_default.desc(), Account.name)
        .all()
    )
    data = [_account_to_dict(a) for a in items]
    cache_set(accounts_key(uid), data, ttl_seconds=300)
    logger.info("List accounts user=%s count=%s", uid, len(data))
    return jsonify(data)


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = (data.get("account_type") or "CHECKING").upper()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error="invalid account_type"), 400
    balance = _parse_balance(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400
    currency = (data.get("currency") or "INR").strip().upper()[:10]
    is_default = bool(data.get("is_default", False))

    # If marked default, clear existing default
    if is_default:
        _clear_default(uid)

    # If user has no accounts yet, make it default
    existing_count = (
        db.session.query(func.count(Account.id))
        .filter_by(user_id=uid, is_active=True)
        .scalar()
    )
    if existing_count == 0:
        is_default = True

    account = Account(
        user_id=uid,
        name=name,
        account_type=account_type,
        balance=balance,
        currency=currency,
        is_default=is_default,
    )
    db.session.add(account)
    db.session.commit()
    _invalidate_account_cache(uid)
    logger.info("Created account id=%s user=%s type=%s", account.id, uid, account_type)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account_type = (data["account_type"] or "").upper()
        if account_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "balance" in data:
        balance = _parse_balance(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "currency" in data:
        account.currency = (data["currency"] or "INR").strip().upper()[:10]
    if "is_default" in data and data["is_default"]:
        _clear_default(uid)
        account.is_default = True
    account.updated_at = datetime.utcnow()
    db.session.commit()
    _invalidate_account_cache(uid)
    logger.info("Updated account id=%s user=%s", account.id, uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404
    # Soft delete
    account.is_active = False
    account.updated_at = datetime.utcnow()
    # If this was the default, promote another account
    if account.is_default:
        account.is_default = False
        next_default = (
            db.session.query(Account)
            .filter(
                Account.user_id == uid,
                Account.is_active.is_(True),
                Account.id != account_id,
            )
            .order_by(Account.created_at)
            .first()
        )
        if next_default:
            next_default.is_default = True
    db.session.commit()
    _invalidate_account_cache(uid)
    logger.info("Soft-deleted account id=%s user=%s", account.id, uid)
    return jsonify(message="deleted")


@bp.get("/<int:account_id>/summary")
@jwt_required()
def account_summary(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404

    from datetime import date as date_cls

    ym = (request.args.get("month") or date_cls.today().strftime("%Y-%m")).strip()

    key = account_summary_key(uid, account_id, ym)
    cached = cache_get(key)
    if cached is not None:
        return jsonify(cached)

    year, month = map(int, ym.split("-"))

    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == account_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == account_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    category_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.account_id == account_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    total_exp = float(expenses or 0)
    payload = {
        "account": _account_to_dict(account),
        "period": {"month": ym},
        "summary": {
            "monthly_income": float(income or 0),
            "monthly_expenses": total_exp,
            "net_flow": round(float(income or 0) - total_exp, 2),
        },
        "category_breakdown": [
            {
                "category_id": r.category_id,
                "category_name": r.category_name,
                "amount": float(r.total_amount or 0),
                "share_pct": (
                    round((float(r.total_amount or 0) / total_exp) * 100, 2)
                    if total_exp > 0
                    else 0
                ),
            }
            for r in category_rows
        ],
    }
    cache_set(key, payload, ttl_seconds=300)
    return jsonify(payload)


def _account_to_dict(a: Account) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "balance": float(a.balance),
        "currency": a.currency,
        "is_default": a.is_default,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _parse_balance(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _clear_default(uid: int):
    db.session.query(Account).filter_by(user_id=uid, is_default=True).update(
        {"is_default": False}
    )


def _invalidate_account_cache(uid: int):
    cache_delete_patterns(
        [
            accounts_key(uid),
            f"user:{uid}:account_summary:*",
            f"user:{uid}:dashboard_overview:*",
            f"user:{uid}:dashboard_summary:*",
        ]
    )
