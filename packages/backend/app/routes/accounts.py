"""
Multi-account financial overview (Issue #132).

Endpoints:
  GET    /accounts                  → list accounts
  POST   /accounts                  → create account
  GET    /accounts/<id>             → get account detail
  PATCH  /accounts/<id>             → update account
  DELETE /accounts/<id>             → delete account (soft: deactivate)
  GET    /accounts/overview         → aggregate view across all accounts
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import case, func

from ..extensions import db
from ..models import Account, AccountType, Expense

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

_VALID_TYPES = {t.value for t in AccountType}


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .order_by(Account.created_at.asc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    account_type = (data.get("account_type") or AccountType.BANK.value).upper()
    if account_type not in _VALID_TYPES:
        return jsonify(error=f"account_type must be one of: {sorted(_VALID_TYPES)}"), 400

    initial = _parse_amount(data.get("initial_balance", 0))
    if initial is None:
        return jsonify(error="invalid initial_balance"), 400

    account = Account(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=(data.get("currency") or "INR").upper()[:10],
        initial_balance=initial,
        color=data.get("color") or None,
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s type=%s", account.id, uid, name, account_type)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/overview")
@jwt_required()
def overview():
    """
    Aggregate financial overview across all active accounts.
    Returns per-account balance + totals.

    Uses a single GROUP BY query to avoid the N+1 problem: instead of issuing
    two separate SUM queries per account, all income/expense aggregates are
    fetched in one shot and joined back to the account list.
    """
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .order_by(Account.created_at.asc())
        .all()
    )

    # Single aggregation query: SUM income and expenses per account_id in one round-trip.
    agg_rows = (
        db.session.query(
            Expense.account_id,
            func.coalesce(
                func.sum(case((Expense.expense_type == "INCOME", Expense.amount), else_=0)), 0
            ).label("income"),
            func.coalesce(
                func.sum(case((Expense.expense_type == "EXPENSE", Expense.amount), else_=0)), 0
            ).label("expenses"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.account_id.isnot(None),
        )
        .group_by(Expense.account_id)
        .all()
    )
    # Map account_id → (income, expenses)
    agg: dict[int, tuple[Decimal, Decimal]] = {
        row.account_id: (Decimal(str(row.income)), Decimal(str(row.expenses)))
        for row in agg_rows
    }

    account_summaries = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")

    for acc in accounts:
        income, expenses = agg.get(acc.id, (Decimal("0"), Decimal("0")))
        balance = acc.initial_balance + income - expenses

        if acc.account_type == AccountType.CREDIT.value:
            total_liabilities += balance
        else:
            total_assets += balance

        account_summaries.append({
            **_account_to_dict(acc),
            "income": float(income),
            "expenses": float(expenses),
            "balance": float(balance),
        })

    # Unassigned expenses (no account) — two scalars, not per-account, so no N+1 here.
    unassigned_agg = (
        db.session.query(
            func.coalesce(
                func.sum(case((Expense.expense_type == "INCOME", Expense.amount), else_=0)), 0
            ).label("income"),
            func.coalesce(
                func.sum(case((Expense.expense_type == "EXPENSE", Expense.amount), else_=0)), 0
            ).label("expenses"),
        )
        .filter(Expense.user_id == uid, Expense.account_id.is_(None))
        .one()
    )
    unassigned_income = Decimal(str(unassigned_agg.income))
    unassigned_expenses = Decimal(str(unassigned_agg.expenses))

    return jsonify({
        "accounts": account_summaries,
        "summary": {
            "total_assets": float(total_assets),
            "total_liabilities": float(total_liabilities),
            "net_worth": float(total_assets - total_liabilities),
            "unassigned_income": float(unassigned_income),
            "unassigned_expenses": float(unassigned_expenses),
            "account_count": len(accounts),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    })


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    acc = _get_or_404(account_id, uid)
    if acc is None:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(acc))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    acc = _get_or_404(account_id, uid)
    if acc is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        acc.name = name

    if "account_type" in data:
        at = (data["account_type"] or "").upper()
        if at not in _VALID_TYPES:
            return jsonify(error=f"account_type must be one of: {sorted(_VALID_TYPES)}"), 400
        acc.account_type = at

    if "currency" in data:
        acc.currency = (data["currency"] or "INR").upper()[:10]

    if "initial_balance" in data:
        v = _parse_amount(data["initial_balance"])
        if v is None:
            return jsonify(error="invalid initial_balance"), 400
        acc.initial_balance = v

    if "color" in data:
        acc.color = data["color"] or None

    db.session.commit()
    return jsonify(_account_to_dict(acc))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    acc = _get_or_404(account_id, uid)
    if acc is None:
        return jsonify(error="not found"), 404
    # Soft delete — preserve historical expense links
    acc.active = False
    db.session.commit()
    return jsonify(message="account deactivated")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_or_404(account_id: int, user_id: int):
    # Soft-deleted accounts (active=False) are intentionally excluded: a
    # deactivated account is treated as gone from the user's perspective.
    # Historical expense rows that still reference it are preserved in the DB
    # but the account itself is no longer accessible via the API.
    acc = db.session.get(Account, account_id)
    if not acc or acc.user_id != user_id or not acc.active:
        return None
    return acc


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _account_to_dict(acc: Account) -> dict:
    return {
        "id": acc.id,
        "name": acc.name,
        "account_type": acc.account_type,
        "currency": acc.currency,
        "initial_balance": float(acc.initial_balance),
        "color": acc.color,
        "active": acc.active,
        "created_at": acc.created_at.isoformat(),
        "updated_at": acc.updated_at.isoformat(),
    }
