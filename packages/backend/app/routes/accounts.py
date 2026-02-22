"""Financial accounts routes — multi-account overview."""

from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import FinancialAccount
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


def _serialize(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
    }


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=data.get("account_type", "CHECKING"),
        currency=data.get("currency", "USD"),
        balance=Decimal(str(data.get("balance", 0))),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_serialize(account)), 201


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(user_id=uid).order_by(
        FinancialAccount.created_at.desc()
    ).all()
    return jsonify([_serialize(a) for a in accounts])


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first_or_404()
    return jsonify(_serialize(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first_or_404()
    data = request.get_json(force=True)

    if "name" in data:
        account.name = data["name"]
    if "account_type" in data:
        account.account_type = data["account_type"]
    if "currency" in data:
        account.currency = data["currency"]
    if "balance" in data:
        account.balance = Decimal(str(data["balance"]))
    if "is_active" in data:
        account.is_active = data["is_active"]

    db.session.commit()
    return jsonify(_serialize(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(id=account_id, user_id=uid).first_or_404()
    db.session.delete(account)
    db.session.commit()
    return jsonify({"message": "deleted"})


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    """Aggregated view across all accounts."""
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(user_id=uid, is_active=True).all()

    total_balance = sum(float(a.balance) for a in accounts)
    by_type = {}
    by_currency = {}

    for a in accounts:
        by_type.setdefault(a.account_type, 0.0)
        by_type[a.account_type] += float(a.balance)

        by_currency.setdefault(a.currency, 0.0)
        by_currency[a.currency] += float(a.balance)

    return jsonify({
        "total_accounts": len(accounts),
        "total_balance": total_balance,
        "by_type": [{"type": k, "balance": v} for k, v in sorted(by_type.items())],
        "by_currency": [{"currency": k, "balance": v} for k, v in sorted(by_currency.items())],
        "accounts": [_serialize(a) for a in accounts],
    })
