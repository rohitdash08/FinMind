"""CRUD endpoints for financial accounts and multi-account overview."""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import extract, func

from ..extensions import db
from ..models import AccountType, Expense, FinancialAccount

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}

# Accounts whose balances represent liabilities (subtracted from net worth)
LIABILITY_TYPES = {AccountType.CREDIT_CARD.value, AccountType.LOAN.value}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@bp.get("")
@jwt_required()
def list_accounts():
    """Return all financial accounts for the authenticated user."""
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "").lower() == "true"

    q = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_inactive:
        q = q.filter_by(is_active=True)

    accounts = q.order_by(FinancialAccount.created_at.desc()).all()
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    """Create a new financial account."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    account_type = (data.get("account_type") or "CHECKING").upper()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"invalid account_type, must be one of {sorted(VALID_ACCOUNT_TYPES)}"), 400

    balance = _parse_decimal(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        institution=(data.get("institution") or "").strip() or None,
        balance=balance,
        currency=(data.get("currency") or "INR").upper()[:10],
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    """Return a single account."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    """Update an existing financial account."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        account.name = name
    if "account_type" in data:
        at = (data["account_type"] or "").upper()
        if at not in VALID_ACCOUNT_TYPES:
            return jsonify(error=f"invalid account_type"), 400
        account.account_type = at
    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None
    if "balance" in data:
        balance = _parse_decimal(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "currency" in data:
        account.currency = (data["currency"] or "INR").upper()[:10]
    if "is_active" in data:
        account.is_active = bool(data["is_active"])
    if "notes" in data:
        account.notes = (data["notes"] or "").strip() or None

    db.session.commit()
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    """Soft-delete an account (set is_active=False)."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    account.is_active = False
    db.session.commit()
    return jsonify(message="account deactivated")


# ---------------------------------------------------------------------------
# Multi-account overview
# ---------------------------------------------------------------------------


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    """Aggregate financial overview across all active accounts.

    Returns net worth, total assets, total liabilities, per-account
    summaries with income/expense totals for the requested month,
    and a combined recent-transactions feed.
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    year, month = map(int, ym.split("-"))

    # Fetch all active accounts
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )

    total_assets = Decimal(0)
    total_liabilities = Decimal(0)
    per_account = []

    for acct in accounts:
        bal = acct.balance or Decimal(0)
        if acct.account_type in LIABILITY_TYPES:
            total_liabilities += abs(bal)
        else:
            total_assets += bal

        # Per-account income/expenses for the month
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
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
                Expense.account_id == acct.id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        tx_count = (
            db.session.query(func.count(Expense.id))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar()
        )

        per_account.append(
            {
                **_account_to_dict(acct),
                "monthly_income": float(income or 0),
                "monthly_expenses": float(expenses or 0),
                "monthly_net": round(float(income or 0) - float(expenses or 0), 2),
                "transaction_count": tx_count or 0,
            }
        )

    # Aggregate income/expenses across ALL accounts (including unlinked)
    agg_income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    agg_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    # Recent transactions across all accounts
    recent = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid)
        .order_by(Expense.spent_at.desc(), Expense.id.desc())
        .limit(15)
        .all()
    )

    payload = {
        "period": {"month": ym},
        "net_worth": float(total_assets - total_liabilities),
        "total_assets": float(total_assets),
        "total_liabilities": float(total_liabilities),
        "aggregate": {
            "monthly_income": float(agg_income or 0),
            "monthly_expenses": float(agg_expenses or 0),
            "monthly_net": round(float(agg_income or 0) - float(agg_expenses or 0), 2),
        },
        "accounts": per_account,
        "account_count": len(accounts),
        "recent_transactions": [
            {
                "id": e.id,
                "description": e.notes or "Transaction",
                "amount": float(e.amount),
                "date": e.spent_at.isoformat(),
                "type": e.expense_type,
                "currency": e.currency,
                "account_id": e.account_id,
            }
            for e in recent
        ],
    }
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Per-account detail
# ---------------------------------------------------------------------------


@bp.get("/<int:account_id>/transactions")
@jwt_required()
def account_transactions(account_id: int):
    """List transactions linked to a specific account."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    q = (
        db.session.query(Expense)
        .filter_by(user_id=uid, account_id=account_id)
        .order_by(Expense.spent_at.desc(), Expense.id.desc())
    )
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return jsonify(
        [
            {
                "id": e.id,
                "description": e.notes or "Transaction",
                "amount": float(e.amount),
                "date": e.spent_at.isoformat(),
                "type": e.expense_type,
                "currency": e.currency,
                "category_id": e.category_id,
                "account_id": e.account_id,
            }
            for e in items
        ]
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "institution": a.institution,
        "balance": float(a.balance or 0),
        "currency": a.currency,
        "is_active": a.is_active,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _parse_decimal(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year_s, month_s = ym.split("-")
    if not (year_s.isdigit() and month_s.isdigit()):
        return False
    m = int(month_s)
    return 1 <= m <= 12
