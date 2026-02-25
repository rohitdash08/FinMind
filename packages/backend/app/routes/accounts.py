"""Multi-account financial overview dashboard.

Allows users to manage multiple financial accounts and view
a consolidated overview of their finances across all accounts.
"""

from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Expense, FinancialAccount

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {"checking", "savings", "credit", "cash", "investment", "loan", "other"}


@bp.post("")
@jwt_required()
def create_account():
    """Create a new financial account."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    account_type = (data.get("account_type") or "").strip().lower()

    if not name:
        return jsonify(error="name is required"), 400
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"account_type must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency", "INR"),
        balance=Decimal(str(data.get("balance", 0))),
        institution=data.get("institution"),
    )
    db.session.add(account)
    db.session.commit()

    return jsonify(_account_dict(account)), 201


@bp.get("")
@jwt_required()
def list_accounts():
    """List all financial accounts for the user."""
    uid = int(get_jwt_identity())
    active_only = request.args.get("active", "true").lower() == "true"

    query = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if active_only:
        query = query.filter_by(is_active=True)

    accounts = query.order_by(FinancialAccount.created_at).all()
    return jsonify(accounts=[_account_dict(a) for a in accounts])


@bp.get("/overview")
@jwt_required()
def account_overview():
    """Consolidated financial overview across all accounts."""
    uid = int(get_jwt_identity())

    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .all()
    )

    total_balance = sum(float(a.balance) for a in accounts)
    by_type = {}
    for a in accounts:
        by_type.setdefault(a.account_type, []).append(_account_dict(a))

    type_totals = {
        t: {"count": len(accts), "total": f"{sum(float(a['balance']) for a in accts):.2f}"}
        for t, accts in by_type.items()
    }

    # Monthly spending across all accounts (current month)
    today = date.today()
    month_start = today.replace(day=1)
    month_expenses = (
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= month_start,
        )
        .scalar()
    )

    return jsonify(
        total_balance=f"{total_balance:.2f}",
        account_count=len(accounts),
        by_type=type_totals,
        month_spending=str(month_expenses),
        accounts=[_account_dict(a) for a in accounts],
    )


@bp.get("/<int:aid>")
@jwt_required()
def get_account(aid: int):
    """Get account details."""
    uid = int(get_jwt_identity())
    account = db.session.query(FinancialAccount).filter_by(id=aid, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    return jsonify(_account_dict(account))


@bp.patch("/<int:aid>")
@jwt_required()
def update_account(aid: int):
    """Update account details."""
    uid = int(get_jwt_identity())
    account = db.session.query(FinancialAccount).filter_by(id=aid, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        account.name = data["name"]
    if "balance" in data:
        account.balance = Decimal(str(data["balance"]))
    if "institution" in data:
        account.institution = data["institution"]
    if "currency" in data:
        account.currency = data["currency"]
    if "is_active" in data:
        account.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify(_account_dict(account))


@bp.delete("/<int:aid>")
@jwt_required()
def delete_account(aid: int):
    """Delete a financial account."""
    uid = int(get_jwt_identity())
    account = db.session.query(FinancialAccount).filter_by(id=aid, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    db.session.delete(account)
    db.session.commit()
    return jsonify(message="account deleted")


@bp.post("/<int:aid>/transfer")
@jwt_required()
def transfer(aid: int):
    """Transfer funds between two accounts."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    to_id = data.get("to_account_id")
    amount = data.get("amount")

    if not to_id or not amount or Decimal(str(amount)) <= 0:
        return jsonify(error="to_account_id and positive amount required"), 400

    from_account = db.session.query(FinancialAccount).filter_by(id=aid, user_id=uid).first()
    to_account = db.session.query(FinancialAccount).filter_by(id=to_id, user_id=uid).first()

    if not from_account or not to_account:
        return jsonify(error="account not found"), 404
    if from_account.id == to_account.id:
        return jsonify(error="cannot transfer to the same account"), 400

    transfer_amount = Decimal(str(amount))
    from_account.balance -= transfer_amount
    to_account.balance += transfer_amount
    db.session.commit()

    return jsonify(
        from_account=_account_dict(from_account),
        to_account=_account_dict(to_account),
        amount=str(transfer_amount),
    )


def _account_dict(account: FinancialAccount) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "balance": str(account.balance),
        "institution": account.institution,
        "is_active": account.is_active,
        "created_at": account.created_at.isoformat() + "Z",
    }
