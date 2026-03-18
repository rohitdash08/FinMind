from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import AccountType, FinancialAccount

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type.value if hasattr(a.account_type, "value") else str(a.account_type),
        "balance": float(a.balance),
        "institution": a.institution,
        "currency": a.currency,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    q = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_inactive:
        q = q.filter(FinancialAccount.is_active.is_(True))
    accounts = q.order_by(FinancialAccount.created_at.asc()).all()
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    raw_type = str(data.get("account_type") or "CHECKING").upper().strip()
    if raw_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"invalid account_type, must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400

    balance = _parse_amount(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=AccountType(raw_type),
        balance=balance,
        institution=(data.get("institution") or "").strip() or None,
        currency=str(data.get("currency") or "INR")[:10],
        is_active=True,
    )
    db.session.add(account)
    db.session.commit()
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
        raw_type = str(data["account_type"] or "").upper().strip()
        if raw_type not in VALID_ACCOUNT_TYPES:
            return jsonify(error=f"invalid account_type, must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400
        account.account_type = AccountType(raw_type)

    if "balance" in data:
        balance = _parse_amount(data["balance"])
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance

    if "institution" in data:
        account.institution = (data["institution"] or "").strip() or None

    if "currency" in data:
        account.currency = str(data["currency"] or "INR")[:10]

    if "is_active" in data:
        account.is_active = bool(data["is_active"])

    account.updated_at = datetime.utcnow()
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
