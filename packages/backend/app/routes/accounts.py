"""
Financial accounts CRUD routes.
Issue #132: Multi-account financial overview dashboard.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, Expense, Bill, ACCOUNT_TYPES
from sqlalchemy import func, extract
from datetime import date
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("")
@jwt_required()
def list_accounts():
    """List all financial accounts for the current user."""
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .order_by(FinancialAccount.created_at)
        .all()
    )
    return jsonify({"accounts": [a.to_dict() for a in accounts]})


@bp.post("")
@jwt_required()
def create_account():
    """Create a new financial account."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    account_type = data.get("account_type", "checking")
    if account_type not in ACCOUNT_TYPES:
        return jsonify(error=f"account_type must be one of {ACCOUNT_TYPES}"), 400
    # Max 20 accounts per user
    count = db.session.query(func.count(FinancialAccount.id)).filter_by(user_id=uid).scalar()
    if count >= 20:
        return jsonify(error="maximum 20 accounts per user"), 400
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency", "INR"),
        opening_balance=float(data.get("opening_balance", 0)),
        color=data.get("color"),
        icon=data.get("icon"),
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", account.id, uid, name)
    return jsonify({"account": account.to_dict()}), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    """Get a specific account with balance summary."""
    uid = int(get_jwt_identity())
    account = _get_account_or_404(account_id, uid)
    if not account:
        return jsonify(error="account not found"), 404
    summary = _account_balance_summary(account)
    return jsonify({"account": account.to_dict(), "summary": summary})


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    """Update account details."""
    uid = int(get_jwt_identity())
    account = _get_account_or_404(account_id, uid)
    if not account:
        return jsonify(error="account not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        account.name = (data["name"] or "").strip() or account.name
    if "account_type" in data and data["account_type"] in ACCOUNT_TYPES:
        account.account_type = data["account_type"]
    if "currency" in data:
        account.currency = data["currency"]
    if "opening_balance" in data:
        account.opening_balance = float(data["opening_balance"])
    if "color" in data:
        account.color = data["color"]
    if "icon" in data:
        account.icon = data["icon"]
    db.session.commit()
    return jsonify({"account": account.to_dict()})


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    """Soft-delete (deactivate) an account."""
    uid = int(get_jwt_identity())
    account = _get_account_or_404(account_id, uid)
    if not account:
        return jsonify(error="account not found"), 404
    account.is_active = False
    db.session.commit()
    return jsonify({"message": "account deactivated"})


@bp.get("/overview")
@jwt_required()
def multi_account_overview():
    """
    Multi-account financial overview for current month.
    Returns all accounts with balances, category breakdowns, and net flow.

    Query params:
      month: YYYY-MM (default: current month)
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if len(ym) != 7 or ym[4] != "-":
        return jsonify(error="invalid month, expected YYYY-MM"), 400
    year, month = map(int, ym.split("-"))
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .order_by(FinancialAccount.created_at)
        .all()
    )
    # For each account compute summary
    account_summaries = []
    total_net_flow = 0.0
    total_income = 0.0
    total_expenses = 0.0
    for account in accounts:
        summary = _account_monthly_summary(account, uid, year, month)
        account_summaries.append({
            "account": account.to_dict(),
            "current_balance": summary["current_balance"],
            "monthly_income": summary["income"],
            "monthly_expenses": summary["expenses"],
            "net_flow": summary["income"] - summary["expenses"],
        })
        total_income += summary["income"]
        total_expenses += summary["expenses"]
        total_net_flow += summary["income"] - summary["expenses"]
    # Unlinked expenses (no account_id set) as a catch-all
    return jsonify({
        "period": {"month": ym},
        "accounts": account_summaries,
        "totals": {
            "total_accounts": len(accounts),
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_flow": round(total_net_flow, 2),
        },
    })


def _get_account_or_404(account_id: int, user_id: int):
    return (
        db.session.query(FinancialAccount)
        .filter_by(id=account_id, user_id=user_id)
        .first()
    )


def _account_balance_summary(account: FinancialAccount) -> dict:
    """Compute current balance = opening_balance + sum(income) - sum(expenses)."""
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == account.user_id, Expense.expense_type == "INCOME")
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == account.user_id, Expense.expense_type != "INCOME")
        .scalar()
    )
    balance = float(account.opening_balance) + float(income) - float(expenses)
    return {
        "current_balance": round(balance, 2),
        "total_income": float(income),
        "total_expenses": float(expenses),
    }


def _account_monthly_summary(account: FinancialAccount, user_id: int, year: int, month: int) -> dict:
    """Monthly income and expenses for an account."""
    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    current_balance = float(account.opening_balance) + income - expenses
    return {"income": round(income, 2), "expenses": round(expenses, 2), "current_balance": round(current_balance, 2)}