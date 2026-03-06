from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, User
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_ACCOUNT_TYPES = {"checking", "savings", "credit", "investment"}


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = (data.get("account_type") or "").strip().lower()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error="invalid account_type"), 400
    try:
        balance = float(data.get("balance", 0))
    except (ValueError, TypeError):
        return jsonify(error="invalid balance"), 400
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        institution=(data.get("institution") or "").strip() or None,
        balance=balance,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        is_active=True,
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", account.id, uid, name)
    return jsonify(_account_to_dict(account)), 201


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .order_by(FinancialAccount.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in items])


@bp.get("/overview")
@jwt_required()
def overview():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .all()
    )
    total_balance = sum(a.balance for a in items)
    by_type = {}
    by_currency = {}
    for a in items:
        by_type[a.account_type] = by_type.get(a.account_type, 0) + a.balance
        by_currency[a.currency] = by_currency.get(a.currency, 0) + a.balance
    return jsonify(
        total_balance=total_balance,
        account_count=len(items),
        by_type=by_type,
        by_currency=by_currency,
    )


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account))


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account_type = (data["account_type"] or "").strip().lower()
        if account_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None
    if "balance" in data:
        try:
            account.balance = float(data["balance"])
        except (ValueError, TypeError):
            return jsonify(error="invalid balance"), 400
    if "currency" in data:
        account.currency = str(data["currency"] or "INR")[:3]
    db.session.commit()
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid or not account.is_active:
        return jsonify(error="not found"), 404
    account.is_active = False
    db.session.commit()
    logger.info("Soft-deleted account id=%s user=%s", account_id, uid)
    return jsonify(message="deleted")


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "institution": a.institution,
        "balance": a.balance,
        "currency": a.currency,
        "is_active": a.is_active,
    }
