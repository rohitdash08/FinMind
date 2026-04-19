from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, AccountType, User
from decimal import Decimal, InvalidOperation
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("/")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = db.session.query(FinancialAccount).filter_by(user_id=uid).all()
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("/")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
        
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=AccountType(data.get("account_type", "BANK")),
        balance=Decimal(str(data.get("balance", 0))),
        currency=data.get("currency", "INR")
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
        account.name = data["name"]
    if "balance" in data:
        account.balance = Decimal(str(data["balance"]))
    if "account_type" in data:
        account.account_type = AccountType(data["account_type"])
        
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


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type.value,
        "balance": float(a.balance),
        "currency": a.currency,
        "created_at": a.created_at.isoformat()
    }
