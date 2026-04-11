from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, AccountType, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


def _serialize(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "balance": float(a.balance),
        "currency": a.currency,
        "active": a.active,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


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
    logger.info("List accounts user=%s count=%s", uid, len(items))
    return jsonify([_serialize(a) for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    if not data.get("name"):
        return jsonify(error="name is required"), 400

    account_type = data.get("account_type", "CHECKING")
    if account_type not in [t.value for t in AccountType]:
        return jsonify(error=f"Invalid account_type. Must be one of: {[t.value for t in AccountType]}"), 400

    a = FinancialAccount(
        user_id=uid,
        name=data["name"],
        account_type=account_type,
        balance=data.get("balance", 0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
    )
    db.session.add(a)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", a.id, uid, a.name)
    cache_delete_patterns([f"user:{uid}:accounts_overview*"])
    return jsonify(_serialize(a)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(FinancialAccount, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_serialize(a))


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(FinancialAccount, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        a.name = data["name"]
    if "account_type" in data:
        if data["account_type"] not in [t.value for t in AccountType]:
            return jsonify(error=f"Invalid account_type. Must be one of: {[t.value for t in AccountType]}"), 400
        a.account_type = data["account_type"]
    if "balance" in data:
        a.balance = data["balance"]
    if "currency" in data:
        a.currency = data["currency"]

    db.session.commit()
    logger.info("Updated account id=%s user=%s", a.id, uid)
    cache_delete_patterns([f"user:{uid}:accounts_overview*"])
    return jsonify(_serialize(a))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(FinancialAccount, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404

    a.active = False
    db.session.commit()
    logger.info("Soft-deleted account id=%s user=%s", a.id, uid)
    cache_delete_patterns([f"user:{uid}:accounts_overview*"])
    return jsonify(message="deleted")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.name)
        .all()
    )

    accounts = [_serialize(a) for a in items]

    # Aggregate balances by type
    by_type: dict[str, float] = {}
    total_assets = 0.0
    total_liabilities = 0.0

    for a in items:
        balance = float(a.balance)
        atype = a.account_type
        by_type[atype] = by_type.get(atype, 0) + balance

        if atype == AccountType.CREDIT.value:
            total_liabilities += abs(balance)
        else:
            total_assets += balance

    net_worth = total_assets - total_liabilities

    logger.info("Accounts overview user=%s accounts=%s net_worth=%s", uid, len(items), net_worth)
    return jsonify(
        {
            "accounts": accounts,
            "summary": {
                "total_accounts": len(items),
                "total_assets": round(total_assets, 2),
                "total_liabilities": round(total_liabilities, 2),
                "net_worth": round(net_worth, 2),
                "by_type": {k: round(v, 2) for k, v in by_type.items()},
            },
        }
    )
