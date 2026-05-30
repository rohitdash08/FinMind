from datetime import date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Account, Expense, Bill, User
from ..services.cache import cache_get, cache_set, cache_delete_patterns
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_ACCOUNT_TYPES = {"CHECKING", "SAVINGS", "CREDIT_CARD", "CASH", "INVESTMENT", "OTHER"}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid)
        .order_by(Account.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = str(data.get("account_type") or "").upper().strip()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"account_type must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400
    balance = _parse_amount(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400
    is_default = bool(data.get("is_default", False))
    if is_default:
        _clear_default_flag(uid)
    account = Account(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        balance=balance,
        is_default=is_default,
        icon=data.get("icon"),
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", account.id, uid, name)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    cache_key = f"user:{uid}:accounts_overview"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid)
        .all()
    )
    if not accounts:
        result = {
            "total_balance": 0.0,
            "accounts": [],
            "balance_by_type": {},
            "balance_by_currency": {},
            "net_worth": 0.0,
        }
        cache_set(cache_key, result, ttl_seconds=120)
        return jsonify(result)

    balance_by_type: dict[str, float] = {}
    balance_by_currency: dict[str, float] = {}
    total_balance = 0.0
    net_worth = 0.0
    account_list = []

    for acct in accounts:
        bal = float(acct.balance)
        account_list.append(_account_to_dict(acct))
        total_balance += bal
        balance_by_type[acct.account_type] = balance_by_type.get(acct.account_type, 0.0) + bal
        balance_by_currency[acct.currency] = balance_by_currency.get(acct.currency, 0.0) + bal
        if acct.account_type in ("CHECKING", "SAVINGS", "CASH", "INVESTMENT"):
            net_worth += bal
        elif acct.account_type == "CREDIT_CARD":
            net_worth -= bal

    result = {
        "total_balance": round(total_balance, 2),
        "accounts": account_list,
        "balance_by_type": {k: round(v, 2) for k, v in balance_by_type.items()},
        "balance_by_currency": {k: round(v, 2) for k, v in balance_by_currency.items()},
        "net_worth": round(net_worth, 2),
    }
    cache_set(cache_key, result, ttl_seconds=120)
    return jsonify(result)


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        account.name = name
    if "account_type" in data:
        at = str(data["account_type"]).upper().strip()
        if at not in VALID_ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = at
    if "balance" in data:
        balance = _parse_amount(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "is_default" in data:
        if data["is_default"]:
            _clear_default_flag(uid)
        account.is_default = bool(data["is_default"])
    if "icon" in data:
        account.icon = data.get("icon")
    db.session.commit()
    _invalidate_cache(uid)
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
    _invalidate_cache(uid)
    return jsonify(message="deleted")


@bp.get("/<int:account_id>/transactions")
@jwt_required()
def account_transactions(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400
    items = (
        db.session.query(Expense)
        .filter_by(user_id=uid, account_id=account_id)
        .order_by(Expense.spent_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify([
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "description": e.notes or "",
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in items
    ])


def _account_to_dict(acct: Account) -> dict:
    return {
        "id": acct.id,
        "name": acct.name,
        "account_type": acct.account_type,
        "currency": acct.currency,
        "balance": float(acct.balance),
        "is_default": acct.is_default,
        "icon": acct.icon,
        "created_at": acct.created_at.isoformat(),
    }


def _clear_default_flag(uid: int):
    db.session.query(Account).filter_by(user_id=uid, is_default=True).update({"is_default": False})


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _invalidate_cache(uid: int):
    cache_delete_patterns([f"user:{uid}:accounts_overview*"])
