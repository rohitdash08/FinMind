"""Multi-account financial overview endpoints.

CRUD operations for financial accounts and an aggregated overview dashboard
that shows all accounts in one view.
"""

from datetime import date
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import FinancialAccount, Expense

bp = Blueprint("accounts", __name__)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@bp.post("")
@jwt_required()
def create_account():
    """Create a new financial account."""
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=data.get("account_type", "CHECKING"),
        balance=data.get("balance", 0),
        currency=data.get("currency", "INR"),
        institution=data.get("institution"),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_serialize(account)), 201


@bp.get("")
@jwt_required()
def list_accounts():
    """List all financial accounts for the authenticated user."""
    uid = int(get_jwt_identity())
    accounts = (
        FinancialAccount.query
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )
    return jsonify([_serialize(a) for a in accounts])


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    """Get a single account by ID."""
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    return jsonify(_serialize(account))


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    """Update an existing account."""
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        account.name = data["name"]
    if "account_type" in data:
        account.account_type = data["account_type"]
    if "balance" in data:
        account.balance = data["balance"]
    if "currency" in data:
        account.currency = data["currency"]
    if "institution" in data:
        account.institution = data["institution"]

    db.session.commit()
    return jsonify(_serialize(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    """Soft-delete an account (marks inactive)."""
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    account.active = False
    db.session.commit()
    return jsonify(message="account deleted"), 200


# ---------------------------------------------------------------------------
# Overview / Dashboard
# ---------------------------------------------------------------------------


@bp.get("/overview")
@jwt_required()
def account_overview():
    """Aggregated multi-account financial overview.

    Returns per-account balances plus combined totals including monthly
    income/expense summaries across all accounts.
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    accounts = (
        FinancialAccount.query
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )

    year, month = map(int, ym.split("-"))

    account_summaries = []
    total_balance = 0.0

    for acct in accounts:
        income = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar() or 0
        )
        expenses = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar() or 0
        )
        bal = float(acct.balance)
        total_balance += bal
        account_summaries.append({
            **_serialize(acct),
            "monthly_income": round(income, 2),
            "monthly_expenses": round(expenses, 2),
            "monthly_net_flow": round(income - expenses, 2),
        })

    # Global totals (including unlinked expenses)
    global_income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar() or 0
    )
    global_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar() or 0
    )

    return jsonify({
        "month": ym,
        "total_balance": round(total_balance, 2),
        "total_accounts": len(accounts),
        "total_monthly_income": round(global_income, 2),
        "total_monthly_expenses": round(global_expenses, 2),
        "total_monthly_net_flow": round(global_income - global_expenses, 2),
        "accounts": account_summaries,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(account: FinancialAccount) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "balance": float(account.balance),
        "currency": account.currency,
        "institution": account.institution,
        "active": account.active,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }
