"""Multi-account financial overview endpoints."""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import FinancialAccount
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_TYPES = {"checking", "savings", "credit", "investment", "cash", "other"}


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "institution": a.institution,
        "active": a.active,
        "created_at": a.created_at.isoformat(),
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid)
        .order_by(FinancialAccount.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    account_type = (data.get("account_type") or "").strip().lower()
    if account_type not in VALID_TYPES:
        return jsonify(error=f"account_type must be one of: {', '.join(sorted(VALID_TYPES))}"), 400
    balance = _parse_amount(data.get("balance", 0)) or Decimal("0")
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency", "INR"),
        balance=balance,
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
    if "balance" in data:
        bal = _parse_amount(data["balance"])
        if bal is None:
            return jsonify(error="invalid balance"), 400
        account.balance = bal
    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None
    if "active" in data:
        account.active = bool(data["active"])
    if "account_type" in data:
        at = (data["account_type"] or "").strip().lower()
        if at not in VALID_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = at
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
    """Aggregated multi-account overview dashboard."""
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .all()
    )
    total_balance = sum(float(a.balance) for a in accounts)
    by_type = {}
    for a in accounts:
        by_type.setdefault(a.account_type, {"count": 0, "total_balance": 0.0})
        by_type[a.account_type]["count"] += 1
        by_type[a.account_type]["total_balance"] += float(a.balance)
    assets = sum(float(a.balance) for a in accounts if a.account_type != "credit")
    liabilities = sum(abs(float(a.balance)) for a in accounts if a.account_type == "credit")
    return jsonify(
        total_accounts=len(accounts),
        total_balance=round(total_balance, 2),
        net_worth=round(assets - liabilities, 2),
        assets=round(assets, 2),
        liabilities=round(liabilities, 2),
        by_type=by_type,
        accounts=[_account_to_dict(a) for a in accounts],
    )
