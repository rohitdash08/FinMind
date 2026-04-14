from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Account, AccountType, Expense

bp = Blueprint("accounts", __name__)


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    q = db.session.query(Account).filter_by(user_id=uid)
    if not include_inactive:
        q = q.filter_by(is_active=True)
    accounts = q.order_by(Account.created_at.desc()).all()
    return jsonify([_serialize(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    account_type = data.get("account_type", "CHECKING").upper()
    if account_type not in AccountType.__members__:
        return jsonify(error=f"invalid account_type, must be one of: {', '.join(AccountType.__members__)}"), 400

    try:
        balance = Decimal(str(data.get("balance", 0)))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify(error="invalid balance"), 400

    account = Account(
        user_id=uid,
        name=name,
        account_type=AccountType(account_type),
        balance=balance,
        currency=data.get("currency", "INR"),
        institution=(data.get("institution") or "").strip() or None,
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_serialize(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    return jsonify(_serialize(account))


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        account.name = name
    if "account_type" in data:
        at = data["account_type"].upper()
        if at not in AccountType.__members__:
            return jsonify(error="invalid account_type"), 400
        account.account_type = AccountType(at)
    if "balance" in data:
        try:
            account.balance = Decimal(str(data["balance"]))
        except (InvalidOperation, TypeError, ValueError):
            return jsonify(error="invalid balance"), 400
    if "currency" in data:
        account.currency = data["currency"]
    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None
    if "is_active" in data:
        account.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify(_serialize(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.query(Account).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="account not found"), 404
    account.is_active = False
    db.session.commit()
    return "", 204


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    """Aggregated multi-account financial overview dashboard."""
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, is_active=True)
        .order_by(Account.created_at.asc())
        .all()
    )

    total_balance = sum(float(a.balance) for a in accounts)
    total_assets = sum(float(a.balance) for a in accounts if float(a.balance) >= 0)
    total_liabilities = sum(float(a.balance) for a in accounts if float(a.balance) < 0)
    net_worth = total_assets + total_liabilities

    # Per-account spending summary (last 30 days)
    from datetime import date, timedelta
    thirty_days_ago = date.today() - timedelta(days=30)

    account_summaries = []
    for a in accounts:
        recent_spending = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == a.id,
                Expense.expense_type != "INCOME",
                Expense.spent_at >= thirty_days_ago,
            )
            .scalar()
        )
        recent_income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == a.id,
                Expense.expense_type == "INCOME",
                Expense.spent_at >= thirty_days_ago,
            )
            .scalar()
        )
        account_summaries.append({
            **_serialize(a),
            "recent_spending_30d": float(recent_spending or 0),
            "recent_income_30d": float(recent_income or 0),
            "recent_net_30d": round(float(recent_income or 0) - float(recent_spending or 0), 2),
        })

    # Breakdown by account type
    type_totals = {}
    for a in accounts:
        t = a.account_type.value
        type_totals[t] = type_totals.get(t, 0) + float(a.balance)

    return jsonify({
        "total_balance": round(total_balance, 2),
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "net_worth": round(net_worth, 2),
        "account_count": len(accounts),
        "accounts": account_summaries,
        "by_type": [{"type": k, "total": round(v, 2)} for k, v in type_totals.items()],
    })


def _serialize(a: Account) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type.value,
        "balance": float(a.balance),
        "currency": a.currency,
        "institution": a.institution,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
