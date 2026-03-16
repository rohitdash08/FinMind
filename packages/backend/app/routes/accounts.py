"""Multi-account financial overview endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, FinancialAccount

bp = Blueprint("accounts", __name__)

VALID_TYPES = {"CHECKING", "SAVINGS", "CREDIT", "CASH", "INVESTMENT", "OTHER"}


def _balance(account: FinancialAccount) -> float:
    """Current balance = initial_balance + income - expenses."""
    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.account_id == account.id,
            Expense.expense_type == "INCOME",
        )
        .scalar()
        or 0
    )
    expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.account_id == account.id,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )
    return round(float(account.initial_balance) + income - expenses, 2)


def _account_json(a: FinancialAccount, *, include_balance: bool = True) -> dict:
    d = {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "initial_balance": float(a.initial_balance),
        "color": a.color,
        "active": a.active,
        "created_at": a.created_at.isoformat(),
    }
    if include_balance:
        d["current_balance"] = _balance(a)
    return d


# ── CRUD ─────────────────────────────────────────────────────────────────────


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        FinancialAccount.query.filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )
    return jsonify([_account_json(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    account_type = (data.get("account_type") or "CHECKING").upper()
    if account_type not in VALID_TYPES:
        return jsonify(error=f"account_type must be one of {sorted(VALID_TYPES)}"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency", "INR"),
        initial_balance=float(data.get("initial_balance", 0)),
        color=data.get("color"),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_account_json(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    result = _account_json(account)
    # Recent transactions for this account
    recent = (
        Expense.query.filter_by(account_id=account_id)
        .order_by(Expense.spent_at.desc(), Expense.id.desc())
        .limit(20)
        .all()
    )
    result["recent_transactions"] = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "expense_type": e.expense_type,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in recent
    ]
    return jsonify(result)


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    data = request.get_json(force=True)
    if "name" in data:
        account.name = data["name"]
    if "account_type" in data:
        at = data["account_type"].upper()
        if at not in VALID_TYPES:
            return jsonify(error=f"account_type must be one of {sorted(VALID_TYPES)}"), 400
        account.account_type = at
    if "color" in data:
        account.color = data["color"]
    if "initial_balance" in data:
        account.initial_balance = float(data["initial_balance"])

    db.session.commit()
    return jsonify(_account_json(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    account.active = False  # soft delete
    db.session.commit()
    return jsonify(message="account deactivated"), 200


# ── Overview  ─────────────────────────────────────────────────────────────────


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    """Aggregate view of all accounts: total balance, by-type breakdown, net worth."""
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(user_id=uid, active=True).all()

    by_type: dict[str, dict] = {}
    total_assets = 0.0
    total_liabilities = 0.0

    account_summaries = []
    for a in accounts:
        bal = _balance(a)
        entry = {**_account_json(a, include_balance=False), "current_balance": bal}
        account_summaries.append(entry)

        if a.account_type not in by_type:
            by_type[a.account_type] = {"count": 0, "total_balance": 0.0}
        by_type[a.account_type]["count"] += 1
        by_type[a.account_type]["total_balance"] = round(
            by_type[a.account_type]["total_balance"] + bal, 2
        )

        if a.account_type == "CREDIT":
            total_liabilities += abs(min(0.0, bal))
        else:
            total_assets += bal

    return jsonify(
        {
            "accounts": account_summaries,
            "by_type": by_type,
            "total_assets": round(total_assets, 2),
            "total_liabilities": round(total_liabilities, 2),
            "net_worth": round(total_assets - total_liabilities, 2),
            "account_count": len(accounts),
        }
    )
