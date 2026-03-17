"""
Multi-account financial overview  (Issue #132 — $200 Bounty).

Endpoints
---------
GET    /accounts              list active accounts
POST   /accounts              create account
GET    /accounts/overview     aggregate overview across all accounts
GET    /accounts/<id>         account detail + recent transactions
PATCH  /accounts/<id>         update account
DELETE /accounts/<id>         deactivate account (soft delete)
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import AccountType, Expense, FinancialAccount

bp = Blueprint("accounts", __name__)
log = logging.getLogger("finmind.accounts")

_VALID_TYPES = {t.value for t in AccountType}
_VALID_CURRENCIES = {"INR", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "SGD", "AED"}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _account_balance(account: FinancialAccount) -> Decimal:
    """initial_balance + all INCOME credits − all EXPENSE debits for this account."""
    result = db.session.query(
        func.coalesce(
            func.sum(
                db.case(
                    (Expense.expense_type == "INCOME", Expense.amount),
                    else_=-Expense.amount,
                )
            ),
            Decimal("0"),
        )
    ).filter(
        Expense.account_id == account.id
    ).scalar()
    return (account.initial_balance or Decimal("0")) + (result or Decimal("0"))


def _account_to_dict(account: FinancialAccount, include_balance: bool = False) -> dict:
    d = {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "initial_balance": float(account.initial_balance),
        "color": account.color,
        "active": account.active,
        "created_at": account.created_at.isoformat(),
    }
    if include_balance:
        d["current_balance"] = float(_account_balance(account))
    return d


def _owned(account_id: int, user_id: int) -> FinancialAccount | None:
    return FinancialAccount.query.filter_by(id=account_id, user_id=user_id, active=True).first()


# ──────────────────────────────────────────────────────────────────────────────
# List
# ──────────────────────────────────────────────────────────────────────────────

@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        FinancialAccount.query
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )
    return jsonify([_account_to_dict(a, include_balance=True) for a in accounts])


# ──────────────────────────────────────────────────────────────────────────────
# Create
# ──────────────────────────────────────────────────────────────────────────────

@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    account_type = (data.get("account_type") or AccountType.BANK.value).upper()
    if account_type not in _VALID_TYPES:
        return jsonify({"error": f"account_type must be one of {sorted(_VALID_TYPES)}"}), 400

    currency = (data.get("currency") or "INR").upper()

    try:
        initial_balance = Decimal(str(data.get("initial_balance", 0)))
    except InvalidOperation:
        return jsonify({"error": "initial_balance must be a number"}), 400

    color = (data.get("color") or "").strip() or None

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=currency,
        initial_balance=initial_balance,
        color=color,
    )
    db.session.add(account)
    db.session.commit()
    log.info("user=%s created account id=%s name=%s", uid, account.id, name)
    return jsonify(_account_to_dict(account, include_balance=True)), 201


# ──────────────────────────────────────────────────────────────────────────────
# Overview  (aggregated across all accounts)
# ──────────────────────────────────────────────────────────────────────────────

@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(user_id=uid, active=True).all()

    if not accounts:
        return jsonify({
            "total_balance": 0.0,
            "total_income": 0.0,
            "total_spent": 0.0,
            "net_flow": 0.0,
            "accounts": [],
            "top_spending_account": None,
        })

    account_ids = [a.id for a in accounts]

    # All-time totals per account
    rows = (
        db.session.query(
            Expense.account_id,
            Expense.expense_type,
            func.coalesce(func.sum(Expense.amount), Decimal("0")).label("total"),
        )
        .filter(Expense.account_id.in_(account_ids))
        .group_by(Expense.account_id, Expense.expense_type)
        .all()
    )

    by_account: dict[int, dict] = {a.id: {"income": Decimal("0"), "spent": Decimal("0")} for a in accounts}
    for row in rows:
        if row.account_id in by_account:
            key = "income" if row.expense_type == "INCOME" else "spent"
            by_account[row.account_id][key] += row.total

    account_summaries = []
    total_balance = Decimal("0")
    total_income = Decimal("0")
    total_spent = Decimal("0")
    top_name: str | None = None
    top_spent = Decimal("-1")

    for a in accounts:
        info = by_account[a.id]
        balance = (a.initial_balance or Decimal("0")) + info["income"] - info["spent"]
        total_balance += balance
        total_income += info["income"]
        total_spent += info["spent"]
        if info["spent"] > top_spent:
            top_spent = info["spent"]
            top_name = a.name

        account_summaries.append({
            **_account_to_dict(a),
            "current_balance": float(balance),
            "total_income": float(info["income"]),
            "total_spent": float(info["spent"]),
        })

    # Recent transactions across all accounts (last 10)
    recent = (
        Expense.query
        .filter(Expense.account_id.in_(account_ids))
        .order_by(Expense.spent_at.desc(), Expense.created_at.desc())
        .limit(10)
        .all()
    )

    recent_txns = [
        {
            "id": e.id,
            "account_id": e.account_id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat() if e.spent_at else None,
        }
        for e in recent
    ]

    return jsonify({
        "total_balance": float(total_balance),
        "total_income": float(total_income),
        "total_spent": float(total_spent),
        "net_flow": float(total_income - total_spent),
        "top_spending_account": top_name if top_spent > 0 else None,
        "accounts": account_summaries,
        "recent_transactions": recent_txns,
    })


# ──────────────────────────────────────────────────────────────────────────────
# Detail
# ──────────────────────────────────────────────────────────────────────────────

@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _owned(account_id, uid)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(_account_to_dict(account, include_balance=True))


# ──────────────────────────────────────────────────────────────────────────────
# Update
# ──────────────────────────────────────────────────────────────────────────────

@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _owned(account_id, uid)
    if not account:
        return jsonify({"error": "Account not found"}), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        account.name = name

    if "account_type" in data:
        t = (data["account_type"] or "").upper()
        if t not in _VALID_TYPES:
            return jsonify({"error": f"account_type must be one of {sorted(_VALID_TYPES)}"}), 400
        account.account_type = t

    if "currency" in data:
        account.currency = (data["currency"] or "INR").upper()

    if "initial_balance" in data:
        try:
            account.initial_balance = Decimal(str(data["initial_balance"]))
        except InvalidOperation:
            return jsonify({"error": "initial_balance must be a number"}), 400

    if "color" in data:
        account.color = (data["color"] or "").strip() or None

    db.session.commit()
    return jsonify(_account_to_dict(account, include_balance=True))


# ──────────────────────────────────────────────────────────────────────────────
# Delete (soft)
# ──────────────────────────────────────────────────────────────────────────────

@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _owned(account_id, uid)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    account.active = False
    db.session.commit()
    return "", 204
