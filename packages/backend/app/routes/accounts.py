import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, AccountType

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid)
        .order_by(FinancialAccount.created_at.desc())
        .all()
    )
    logger.info("List accounts for user=%s count=%s", uid, len(items))
    return jsonify([{
        "id": a.id,
        "name": a.name,
        "type": a.type.value,
        "currency": a.currency,
        "balance": float(a.balance) if a.balance is not None else None,
        "created_at": a.created_at.isoformat(),
    } for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        logger.warning("Create account missing name user=%s", uid)
        return jsonify(error="name required"), 400
    acc_type = data.get("type", "BANK")
    if acc_type not in AccountType.__members__:
        return jsonify(error="invalid type"), 400
    currency = data.get("currency", "INR")
    # Optional balance
    balance = data.get("balance")
    if balance is not None:
        try:
            balance = float(balance)
        except ValueError:
            return jsonify(error="invalid balance"), 400
    # Optional: enforce unique name per user? maybe not necessary
    a = FinancialAccount(
        user_id=uid,
        name=name,
        type=AccountType(acc_type),
        currency=currency,
        balance=balance,
    )
    db.session.add(a)
    db.session.commit()
    logger.info("Created account id=%s user=%s", a.id, uid)
    return jsonify({
        "id": a.id,
        "name": a.name,
        "type": a.type.value,
        "currency": a.currency,
        "balance": float(a.balance) if a.balance is not None else None,
        "created_at": a.created_at.isoformat(),
    }), 201


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(FinancialAccount, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        a.name = name
    if "type" in data:
        acc_type = data.get("type")
        if acc_type not in AccountType.__members__:
            return jsonify(error="invalid type"), 400
        a.type = AccountType(acc_type)
    if "currency" in data:
        a.currency = data.get("currency")
    if "balance" in data:
        balance = data.get("balance")
        if balance is None:
            a.balance = None
        else:
            try:
                a.balance = float(balance)
            except ValueError:
                return jsonify(error="invalid balance"), 400
    db.session.commit()
    logger.info("Updated account id=%s user=%s", a.id, uid)
    return jsonify({
        "id": a.id,
        "name": a.name,
        "type": a.type.value,
        "currency": a.currency,
        "balance": float(a.balance) if a.balance is not None else None,
        "created_at": a.created_at.isoformat(),
    })


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(FinancialAccount, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(a)
    db.session.commit()
    logger.info("Deleted account id=%s user=%s", a.id, uid)
    return jsonify(message="deleted")