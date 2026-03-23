from collections import defaultdict
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AccountType, FinancialAccount, Expense, Bill, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

MAX_NAME_LENGTH = 200
MAX_INSTITUTION_LENGTH = 200
MAX_ACCOUNTS_PER_USER = 50
VALID_ACCOUNT_TYPES = frozenset(t.value for t in AccountType)


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
    if len(name) > MAX_NAME_LENGTH:
        return jsonify(error="name too long"), 400

    account_type = str(data.get("account_type") or "CHECKING").upper()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error="invalid account_type"), 400

    balance = _parse_amount(data.get("balance") or 0) or Decimal("0")

    currency = (data.get("currency") or "").strip().upper()
    if not currency:
        currency = user.preferred_currency if user else "INR"
    currency = currency[:10]

    institution = (data.get("institution") or "").strip() or None
    if institution and len(institution) > MAX_INSTITUTION_LENGTH:
        return jsonify(error="institution name too long"), 400

    # Guard against unbounded account creation
    existing_count = (
        db.session.query(db.func.count(FinancialAccount.id))
        .filter_by(user_id=uid)
        .scalar()
    )
    if existing_count >= MAX_ACCOUNTS_PER_USER:
        return jsonify(error="account limit reached"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        balance=balance,
        currency=currency,
        institution=institution,
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s", account.id, uid)
    _invalidate_account_cache(uid)
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
        if len(name) > MAX_NAME_LENGTH:
            return jsonify(error="name too long"), 400
        account.name = name
    if "account_type" in data:
        account_type = str(data["account_type"] or "").upper()
        if account_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "balance" in data:
        balance = _parse_amount(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "currency" in data:
        currency = (str(data["currency"] or "")).strip().upper()
        if not currency:
            return jsonify(error="currency required"), 400
        account.currency = currency[:10]
    if "institution" in data:
        institution = (data["institution"] or "").strip() or None
        if institution and len(institution) > MAX_INSTITUTION_LENGTH:
            return jsonify(error="institution name too long"), 400
        account.institution = institution
    if "active" in data:
        account.active = bool(data["active"])

    db.session.commit()
    logger.info("Updated account id=%s user=%s", account.id, uid)
    _invalidate_account_cache(uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404

    # Soft-delete by default; pass ?hard=true for permanent removal
    hard = request.args.get("hard", "").lower() == "true"
    if hard:
        db.session.delete(account)
        logger.info("Hard-deleted account id=%s user=%s", account_id, uid)
    else:
        account.active = False
        logger.info("Soft-deleted account id=%s user=%s", account_id, uid)
    db.session.commit()
    _invalidate_account_cache(uid)
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

    # Compute per-currency totals so mixed-currency sums are meaningful
    totals_by_currency: dict[str, float] = defaultdict(float)
    for a in accounts:
        totals_by_currency[a.currency] += float(a.balance)
    # Flat total is still useful when all accounts share a currency
    total_balance = sum(totals_by_currency.values())

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
        "totals_by_currency": dict(totals_by_currency),
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
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        val = Decimal(str(raw)).quantize(Decimal("0.01"))
        # Guard against absurdly large values that could cause overflow
        if abs(val) > Decimal("9999999999.99"):
            return None
        return val
    except (InvalidOperation, ValueError, TypeError):
        return None


def _invalidate_account_cache(uid: int):
    try:
        cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    except Exception:
        pass  # Cache invalidation is best-effort
