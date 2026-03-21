from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AccountType, FinancialAccount, Expense, Bill, User
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "").lower() == "true"
    q = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_inactive:
        q = q.filter_by(active=True)
    items = q.order_by(FinancialAccount.created_at.desc()).all()
    logger.info("List accounts user=%s count=%s", uid, len(items))
    return jsonify([_account_to_dict(a) for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = str(data.get("account_type") or "CHECKING").upper()
    if account_type not in {t.value for t in AccountType}:
        return jsonify(error="invalid account_type"), 400
    balance = _parse_amount(data.get("balance") or 0) or Decimal("0")
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        balance=balance,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        institution=(data.get("institution") or "").strip() or None,
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s", account.id, uid)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account_type = str(data["account_type"] or "").upper()
        if account_type not in {t.value for t in AccountType}:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "balance" in data:
        balance = _parse_amount(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "currency" in data:
        account.currency = str(data["currency"] or "INR")[:10]
    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None
    if "active" in data:
        account.active = bool(data["active"])
    db.session.commit()
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(account)
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.desc())
        .all()
    )
    total_balance = sum(float(a.balance) for a in accounts)
    recent_expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at.desc())
        .limit(5)
        .all()
    )
    upcoming_bills = (
        db.session.query(Bill)
        .filter_by(user_id=uid, active=True)
        .order_by(Bill.next_due_date)
        .limit(5)
        .all()
    )
    return jsonify({
        "accounts": [_account_to_dict(a) for a in accounts],
        "total_balance": total_balance,
        "account_count": len(accounts),
        "recent_expenses": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency,
                "description": e.notes or "",
                "date": e.spent_at.isoformat(),
            }
            for e in recent_expenses
        ],
        "upcoming_bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat(),
            }
            for b in upcoming_bills
        ],
    })


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "balance": float(a.balance),
        "currency": a.currency,
        "institution": a.institution,
        "active": a.active,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
