"""Financial accounts CRUD + multi-account overview."""

from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, AccountType, Expense
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}
LIABILITY_TYPES = {AccountType.CREDIT.value}


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "institution": a.institution,
        "last_four": a.last_four,
        "color": a.color,
        "active": a.active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _parse_balance(raw) -> Decimal | None:
    if raw is None:
        return Decimal("0")
    try:
        val = Decimal(str(raw))
        return val
    except (InvalidOperation, ValueError):
        return None


@bp.get("")
@jwt_required()
def list_accounts():
    """List all active financial accounts for the authenticated user."""
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.desc())
        .all()
    )
    logger.info("List accounts user=%s count=%s", uid, len(accounts))
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

    account_type = (data.get("account_type") or AccountType.BANK.value).upper()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"invalid account_type, must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400

    balance = _parse_balance(data.get("balance"))
    if balance is None:
        return jsonify(error="invalid balance"), 400

    currency = (data.get("currency") or "INR").upper()
    if len(currency) > 10:
        return jsonify(error="invalid currency"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=currency,
        balance=balance,
        institution=(data.get("institution") or "").strip() or None,
        last_four=(data.get("last_four") or "").strip()[:4] or None,
        color=data.get("color", "#3B82F6"),
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s type=%s", account.id, uid, account_type)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    """Get a single account by ID."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="account not found"), 404
    return jsonify(_account_to_dict(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    """Update an existing financial account."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="account not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        account.name = name

    if "account_type" in data:
        account_type = data["account_type"].upper()
        if account_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type

    if "currency" in data:
        account.currency = (data["currency"] or "INR").upper()

    if "balance" in data:
        balance = _parse_balance(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance

    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None

    if "last_four" in data:
        account.last_four = (data["last_four"] or "").strip()[:4] or None

    if "color" in data:
        account.color = data["color"]

    db.session.commit()
    logger.info("Updated account id=%s user=%s", account_id, uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    """Soft-delete an account (set active=False)."""
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="account not found"), 404

    account.active = False
    db.session.commit()
    logger.info("Soft-deleted account id=%s user=%s", account_id, uid)
    return jsonify(message="account deactivated"), 200


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    """Aggregated multi-account financial overview.

    Returns total balance, breakdown by account type and currency,
    net worth (assets minus liabilities), and recent transactions.
    """
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .all()
    )

    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    by_type: dict[str, dict] = {}
    by_currency: dict[str, float] = {}

    for a in accounts:
        bal = Decimal(str(a.balance))
        if a.account_type in LIABILITY_TYPES:
            total_liabilities += abs(bal)
        else:
            total_assets += bal

        # Group by type
        if a.account_type not in by_type:
            by_type[a.account_type] = {"count": 0, "total_balance": 0.0}
        by_type[a.account_type]["count"] += 1
        by_type[a.account_type]["total_balance"] += float(bal)

        # Group by currency
        by_currency[a.currency] = by_currency.get(a.currency, 0.0) + float(bal)

    net_worth = float(total_assets - total_liabilities)

    # Recent expenses across all user expenses (last 10)
    recent_expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at.desc())
        .limit(10)
        .all()
    )
    recent = [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "notes": e.notes,
            "date": e.spent_at.isoformat() if e.spent_at else None,
        }
        for e in recent_expenses
    ]

    overview = {
        "total_accounts": len(accounts),
        "total_assets": float(total_assets),
        "total_liabilities": float(total_liabilities),
        "net_worth": net_worth,
        "by_type": by_type,
        "by_currency": by_currency,
        "accounts": [_account_to_dict(a) for a in accounts],
        "recent_transactions": recent,
    }
    logger.info("Overview user=%s accounts=%s net_worth=%s", uid, len(accounts), net_worth)
    return jsonify(overview)
