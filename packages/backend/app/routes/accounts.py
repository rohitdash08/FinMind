"""
Accounts routes — CRUD for financial accounts.

Endpoints:
  GET    /accounts                 List all accounts for the authenticated user
  POST   /accounts                 Create a new account
  GET    /accounts/<id>            Get a single account
  PATCH  /accounts/<id>            Update an account
  DELETE /accounts/<id>            Delete (deactivate) an account
  GET    /accounts/<id>/summary    Per-account financial summary (income/expenses/net)
"""

from datetime import date
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Account, AccountTypeEnum, Expense, Category
from ..services.cache import cache_get, cache_set, cache_delete

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {e.value for e in AccountTypeEnum}


def _account_summary_key(uid: int, account_id: int, ym: str) -> str:
    return f"user:{uid}:account:{account_id}:summary:{ym}"


def _accounts_list_key(uid: int) -> str:
    return f"user:{uid}:accounts"


def _is_valid_month(ym: str) -> bool:
    try:
        parts = ym.split("-")
        if len(parts) != 2:
            return False
        year, month = int(parts[0]), int(parts[1])
        return 1 <= month <= 12 and 2000 <= year <= 2100
    except (ValueError, AttributeError):
        return False


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    cached = cache_get(_accounts_list_key(uid))
    if cached:
        return jsonify(cached)

    accounts = (
        db.session.query(Account)
        .filter(Account.user_id == uid, Account.is_active.is_(True))
        .order_by(Account.created_at.asc())
        .all()
    )
    result = [a.to_dict() for a in accounts]
    cache_set(_accounts_list_key(uid), result, ttl=300)
    return jsonify(result)


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}

    name = (body.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    account_type_raw = (body.get("account_type") or "CHECKING").upper()
    if account_type_raw not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"account_type must be one of {sorted(VALID_ACCOUNT_TYPES)}"), 400

    try:
        balance = float(body.get("balance", 0.0))
    except (TypeError, ValueError):
        return jsonify(error="balance must be a number"), 400

    account = Account(
        user_id=uid,
        name=name,
        account_type=AccountTypeEnum(account_type_raw),
        currency=(body.get("currency") or "USD").upper()[:10],
        balance=balance,
        institution=(body.get("institution") or "").strip() or None,
        notes=(body.get("notes") or "").strip() or None,
        color=(body.get("color") or "").strip() or None,
        is_active=True,
    )
    db.session.add(account)
    db.session.commit()
    cache_delete(_accounts_list_key(uid))
    return jsonify(account.to_dict()), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    return jsonify(account.to_dict())


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    body = request.get_json(silent=True) or {}

    if "name" in body:
        name = (body["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        account.name = name

    if "account_type" in body:
        account_type_raw = (body["account_type"] or "").upper()
        if account_type_raw not in VALID_ACCOUNT_TYPES:
            return jsonify(error=f"account_type must be one of {sorted(VALID_ACCOUNT_TYPES)}"), 400
        account.account_type = AccountTypeEnum(account_type_raw)

    if "currency" in body:
        account.currency = (body["currency"] or "USD").upper()[:10]

    if "balance" in body:
        try:
            account.balance = float(body["balance"])
        except (TypeError, ValueError):
            return jsonify(error="balance must be a number"), 400

    if "institution" in body:
        account.institution = (body["institution"] or "").strip() or None

    if "notes" in body:
        account.notes = (body["notes"] or "").strip() or None

    if "color" in body:
        account.color = (body["color"] or "").strip() or None

    if "is_active" in body:
        account.is_active = bool(body["is_active"])

    db.session.commit()
    cache_delete(_accounts_list_key(uid))
    return jsonify(account.to_dict())


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    # Soft-delete by deactivating
    account.is_active = False
    db.session.commit()
    cache_delete(_accounts_list_key(uid))
    return jsonify({"message": "account deactivated"}), 200


@bp.get("/<int:account_id>/summary")
@jwt_required()
def account_summary(account_id: int):
    """
    Returns financial summary for a specific account, filtered by month.
    Query param: ?month=YYYY-MM  (defaults to current month)
    """
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    cache_key = _account_summary_key(uid, account_id, ym)
    cached = cache_get(cache_key)
    if cached:
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

    total_expenses = float(expenses or 0)
    category_breakdown = [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": float(r.total_amount or 0),
            "share_pct": round(
                float(r.total_amount or 0) / total_expenses * 100, 2
            ) if total_expenses > 0 else 0.0,
        }
        for r in category_rows
    ]

    monthly_income = float(income or 0)
    monthly_expenses = float(expenses or 0)

    payload = {
        "account": account.to_dict(),
        "period": {"month": ym},
        "summary": {
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "net_flow": round(monthly_income - monthly_expenses, 2),
            "current_balance": float(account.balance),
        },
        "category_breakdown": category_breakdown,
    }

    cache_set(cache_key, payload, ttl=900)
    return jsonify(payload)