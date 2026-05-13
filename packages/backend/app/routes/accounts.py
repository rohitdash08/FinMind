from decimal import Decimal, InvalidOperation
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Expense, FinancialAccount, User
from ..services.cache import cache_delete_patterns

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

ACCOUNT_TYPES = {"CHECKING", "SAVINGS", "CREDIT", "CASH", "INVESTMENT", "OTHER"}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.name)
        .all()
    )
    return jsonify([_account_to_dict(account) for account in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    opening_balance = _parse_amount(data.get("opening_balance", 0))
    if opening_balance is None:
        return jsonify(error="invalid opening_balance"), 400
    account_type = _parse_account_type(data.get("account_type"))
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=(data.get("currency") or (user.preferred_currency if user else "INR")),
        opening_balance=opening_balance,
    )
    db.session.add(account)
    db.session.commit()
    _invalidate_account_cache(uid)
    logger.info("Created account id=%s user=%s", account.id, uid)
    return jsonify(_account_to_dict(account)), 201


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid or not account.active:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account.account_type = _parse_account_type(data.get("account_type"))
    if "currency" in data:
        account.currency = str(data.get("currency") or "INR").upper()[:10]
    if "opening_balance" in data:
        opening_balance = _parse_amount(data.get("opening_balance"))
        if opening_balance is None:
            return jsonify(error="invalid opening_balance"), 400
        account.opening_balance = opening_balance
    db.session.commit()
    _invalidate_account_cache(uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid or not account.active:
        return jsonify(error="not found"), 404
    has_transactions = (
        db.session.query(Expense.id)
        .filter_by(user_id=uid, account_id=account.id)
        .first()
        is not None
    )
    if has_transactions:
        account.active = False
    else:
        db.session.delete(account)
    db.session.commit()
    _invalidate_account_cache(uid)
    return jsonify(message="deleted")


def _account_to_dict(account: FinancialAccount) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "opening_balance": float(account.opening_balance or 0),
        "active": account.active,
    }


def _parse_account_type(raw: str | None) -> str:
    value = str(raw or "CHECKING").upper().strip()
    return value if value in ACCOUNT_TYPES else "OTHER"


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _invalidate_account_cache(uid: int):
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
