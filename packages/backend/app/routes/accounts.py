from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import FinancialAccount

bp = Blueprint("accounts", __name__)

VALID_TYPES = {"checking", "savings", "credit"}


def _acct_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "balance": float(a.balance),
        "last_transaction": a.last_transaction,
    }


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accts = db.session.query(FinancialAccount).filter_by(user_id=uid).order_by(FinancialAccount.created_at.desc()).all()
    return jsonify([_acct_to_dict(a) for a in accts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    acct_type = (data.get("account_type") or "").lower()
    if acct_type not in VALID_TYPES:
        return jsonify(error="account_type must be checking, savings, or credit"), 400
    try:
        balance = Decimal(str(data.get("balance", 0))).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return jsonify(error="invalid balance"), 400
    a = FinancialAccount(user_id=uid, name=name, account_type=acct_type, balance=balance)
    db.session.add(a)
    db.session.commit()
    return jsonify(_acct_to_dict(a)), 201
