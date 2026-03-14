from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Account, AccountType, Expense
from ..services.cache import cache_get, cache_set, cache_delete_patterns, accounts_overview_key

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    account_type = (data.get("account_type") or "").upper().strip()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"invalid account_type, must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400

    balance = _parse_amount(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400

    is_default = bool(data.get("is_default", False))

    # If this is set as default, unset any existing default
    if is_default:
        _clear_defaults(uid)

    account = Account(
        user_id=uid,
        name=name,
        account_type=AccountType(account_type),
        institution=(data.get("institution") or "").strip() or None,
        currency=(data.get("currency") or "INR").upper().strip()[:10],
        balance=balance,
        is_default=is_default,
    )
    db.session.add(account)
    db.session.commit()

    _invalidate_overview_cache(uid)
    return jsonify(_account_to_dict(account)), 201


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .order_by(Account.is_default.desc(), Account.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())

    key = accounts_overview_key(uid)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    today = date.today()
    year, month = today.year, today.month

    # Previous month for month-over-month comparison
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .order_by(Account.is_default.desc(), Account.created_at.desc())
        .all()
    )

    total_balance = 0.0
    total_assets = 0.0
    total_liabilities = 0.0
    account_breakdowns = []

    for acct in accounts:
        balance = float(acct.balance)
        total_balance += balance

        # Credit card balances represent liabilities (negative net worth)
        if acct.account_type == AccountType.CREDIT_CARD:
            total_liabilities += abs(balance)
        else:
            total_assets += balance

        # Recent transactions count (last 30 days)
        thirty_days_ago = date(year, month, 1)
        recent_txn_count = (
            db.session.query(func.count(Expense.id))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                Expense.spent_at >= thirty_days_ago,
            )
            .scalar()
        ) or 0

        # Month spending for this account
        month_spending = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )

        account_breakdowns.append({
            "id": acct.id,
            "name": acct.name,
            "account_type": acct.account_type.value,
            "institution": acct.institution,
            "currency": acct.currency,
            "balance": balance,
            "is_default": acct.is_default,
            "recent_transactions_count": recent_txn_count,
            "month_spending": round(month_spending, 2),
        })

    net_worth = round(total_assets - total_liabilities, 2)

    # Current month total spending
    current_month_spending = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    # Previous month total spending
    prev_month_spending = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == prev_year,
            extract("month", Expense.spent_at) == prev_month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    month_over_month_change = round(current_month_spending - prev_month_spending, 2)

    payload = {
        "total_balance": round(total_balance, 2),
        "net_worth": net_worth,
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "month_spending": round(current_month_spending, 2),
        "prev_month_spending": round(prev_month_spending, 2),
        "month_over_month_change": month_over_month_change,
        "accounts_count": len(accounts),
        "accounts": account_breakdowns,
    }

    cache_set(key, payload, ttl_seconds=300)
    return jsonify(payload)


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or not account.active:
        return jsonify(error="not found"), 404
    if account.user_id != uid:
        return jsonify(error="forbidden"), 403

    today = date.today()
    year, month = today.year, today.month

    # Summary stats for this account
    total_expenses = float(
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

    total_income = float(
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

    transaction_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == account_id,
        )
        .scalar()
    ) or 0

    result = _account_to_dict(account)
    result["summary"] = {
        "month_expenses": round(total_expenses, 2),
        "month_income": round(total_income, 2),
        "net_flow": round(total_income - total_expenses, 2),
        "total_transactions": transaction_count,
    }
    return jsonify(result)


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or not account.active:
        return jsonify(error="not found"), 404
    if account.user_id != uid:
        return jsonify(error="forbidden"), 403

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name

    if "account_type" in data:
        account_type = (data["account_type"] or "").upper().strip()
        if account_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error=f"invalid account_type"), 400
        account.account_type = AccountType(account_type)

    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None

    if "currency" in data:
        account.currency = (data["currency"] or "INR").upper().strip()[:10]

    if "balance" in data:
        balance = _parse_amount(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance

    if "is_default" in data:
        is_default = bool(data["is_default"])
        if is_default:
            _clear_defaults(uid)
        account.is_default = is_default

    account.updated_at = datetime.utcnow()
    db.session.commit()

    _invalidate_overview_cache(uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or not account.active:
        return jsonify(error="not found"), 404
    if account.user_id != uid:
        return jsonify(error="forbidden"), 403

    account.active = False
    account.updated_at = datetime.utcnow()
    db.session.commit()

    _invalidate_overview_cache(uid)
    return jsonify(message="deleted")


def _account_to_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type.value,
        "institution": account.institution,
        "currency": account.currency,
        "balance": float(account.balance),
        "is_default": account.is_default,
        "active": account.active,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _clear_defaults(uid: int):
    """Unset is_default for all user's accounts."""
    db.session.query(Account).filter_by(user_id=uid, is_default=True).update(
        {"is_default": False}
    )


def _invalidate_overview_cache(uid: int):
    cache_delete_patterns([
        accounts_overview_key(uid),
        f"user:{uid}:dashboard_summary:*",
    ])
