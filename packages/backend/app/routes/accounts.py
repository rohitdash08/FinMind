"""Financial accounts API."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount
from datetime import datetime
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(user_id=uid, active=True).all()
    return jsonify({
        "accounts": [{
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "balance": float(a.balance),
            "currency": a.currency,
        } for a in accounts]
    })


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Account name is required"}), 400
    account = FinancialAccount(
        user_id=uid, name=name,
        account_type=data.get("account_type", "checking"),
        balance=float(data.get("balance", 0)),
        currency=data.get("currency", "INR"),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify({"id": account.id, "name": account.name}), 201


@bp.get("/consolidated")
@jwt_required()
def consolidated_view():
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(user_id=uid, active=True).all()
    total = sum(float(a.balance) for a in accounts)
    by_type = {}
    for a in accounts:
        t = a.account_type
        by_type[t] = by_type.get(t, 0) + float(a.balance)
    return jsonify({
        "total_balance": round(total, 2),
        "account_count": len(accounts),
        "by_type": {k: round(v, 2) for k, v in by_type.items()},
        "accounts": [{
            "id": a.id, "name": a.name, "type": a.account_type,
            "balance": float(a.balance), "currency": a.currency,
        } for a in accounts],
    })


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify({"error": "Not found"}), 404
    account.active = False
    db.session.commit()
    return jsonify({"ok": True})