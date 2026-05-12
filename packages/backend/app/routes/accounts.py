from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Account, Expense

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {"checking", "savings", "credit_card", "cash", "investment"}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .order_by(Account.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = (data.get("account_type") or "checking").lower()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error="invalid account_type"), 400
    currency = (data.get("currency") or "INR").upper()[:3]
    initial_balance = _parse_amount(data.get("initial_balance", 0))
    if initial_balance is None:
        return jsonify(error="invalid initial_balance"), 400
    is_default = bool(data.get("is_default", False))

    # If this is set as default, unset any existing default
    if is_default:
        db.session.query(Account).filter_by(user_id=uid, is_default=True).update(
            {"is_default": False}
        )

    # If user has no active accounts, make this the default
    existing_count = (
        db.session.query(func.count(Account.id))
        .filter_by(user_id=uid, active=True)
        .scalar()
    )
    if existing_count == 0:
        is_default = True

    account = Account(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=currency,
        initial_balance=initial_balance,
        is_default=is_default,
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_account_to_dict(account)), 201


@bp.patch("/<int:id>")
@jwt_required()
def update_account(id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, id)
    if not account or account.user_id != uid or not account.active:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account_type = (data.get("account_type") or "").lower()
        if account_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "currency" in data:
        account.currency = (data.get("currency") or "INR").upper()[:3]
    if "initial_balance" in data:
        initial_balance = _parse_amount(data.get("initial_balance"))
        if initial_balance is None:
            return jsonify(error="invalid initial_balance"), 400
        account.initial_balance = initial_balance
    if "is_default" in data and data["is_default"]:
        db.session.query(Account).filter(
            Account.user_id == uid, Account.id != id, Account.is_default.is_(True)
        ).update({"is_default": False})
        account.is_default = True
    db.session.commit()
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:id>")
@jwt_required()
def delete_account(id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, id)
    if not account or account.user_id != uid or not account.active:
        return jsonify(error="not found"), 404
    account.active = False
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/<int:id>/summary")
@jwt_required()
def account_summary(id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, id)
    if not account or account.user_id != uid or not account.active:
        return jsonify(error="not found"), 404

    today = date.today()
    year, month = today.year, today.month

    total_income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == id,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )

    total_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == id,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    monthly_spend = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.account_id == id,
            Expense.expense_type != "INCOME",
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .scalar()
    )

    recent = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid, Expense.account_id == id)
        .order_by(Expense.spent_at.desc(), Expense.id.desc())
        .limit(10)
        .all()
    )

    balance = float(account.initial_balance or 0) + float(total_income or 0) - float(total_expenses or 0)

    return jsonify(
        {
            "account": _account_to_dict(account),
            "balance": round(balance, 2),
            "total_income": float(total_income or 0),
            "total_expenses": float(total_expenses or 0),
            "monthly_spend": float(monthly_spend or 0),
            "recent_transactions": [
                {
                    "id": e.id,
                    "description": e.notes or "Transaction",
                    "amount": float(e.amount),
                    "date": e.spent_at.isoformat(),
                    "type": e.expense_type,
                    "category_id": e.category_id,
                    "currency": e.currency,
                }
                for e in recent
            ],
        }
    )


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .order_by(Account.created_at.asc())
        .all()
    )

    today = date.today()
    year, month = today.year, today.month
    account_details = []
    total_net_worth = 0.0

    for acct in accounts:
        total_income = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                Expense.expense_type == "INCOME",
            )
            .scalar()
            or 0
        )
        total_expenses = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                Expense.expense_type != "INCOME",
            )
            .scalar()
            or 0
        )
        monthly_spend = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                Expense.expense_type != "INCOME",
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar()
            or 0
        )
        balance = float(acct.initial_balance or 0) + total_income - total_expenses
        total_net_worth += balance
        account_details.append(
            {
                "account": _account_to_dict(acct),
                "balance": round(balance, 2),
                "total_income": total_income,
                "total_expenses": total_expenses,
                "monthly_spend": monthly_spend,
            }
        )

    return jsonify(
        {
            "total_net_worth": round(total_net_worth, 2),
            "accounts": account_details,
        }
    )


def _account_to_dict(a: Account) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "initial_balance": float(a.initial_balance or 0),
        "is_default": a.is_default,
        "active": a.active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
