from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Account, AccountType, Expense, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}


def _account_json(a: Account) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "institution": a.institution,
        "balance": float(a.balance),
        "currency": a.currency,
        "color": a.color,
        "active": a.active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    query = db.session.query(Account).filter_by(user_id=uid)
    if not include_inactive:
        query = query.filter_by(active=True)
    items = query.order_by(Account.created_at.desc()).all()
    logger.info("List accounts user=%s count=%s", uid, len(items))
    return jsonify([_account_json(a) for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify(error="name is required"), 400
    account_type = data.get("account_type", AccountType.BANK.value).upper()
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"account_type must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400
    a = Account(
        user_id=uid,
        name=data["name"],
        account_type=account_type,
        institution=data.get("institution"),
        balance=float(data.get("balance", 0)),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        color=data.get("color", "#3B82F6"),
    )
    db.session.add(a)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", a.id, uid, a.name)
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(_account_json(a)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(Account, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_account_json(a))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(Account, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        a.name = data["name"]
    if "account_type" in data:
        val = data["account_type"].upper()
        if val not in VALID_ACCOUNT_TYPES:
            return jsonify(error=f"account_type must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400
        a.account_type = val
    if "institution" in data:
        a.institution = data["institution"]
    if "balance" in data:
        a.balance = float(data["balance"])
    if "currency" in data:
        a.currency = data["currency"]
    if "color" in data:
        a.color = data["color"]
    if "active" in data:
        a.active = bool(data["active"])
    db.session.commit()
    logger.info("Updated account id=%s user=%s", a.id, uid)
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(_account_json(a))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    a = db.session.get(Account, account_id)
    if not a or a.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(a)
    db.session.commit()
    logger.info("Deleted account id=%s user=%s", a.id, uid)
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(message="deleted")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    """Aggregated multi-account overview: total balance, net worth, breakdown by type."""
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, active=True)
        .all()
    )

    # Group by type
    type_breakdown = {}
    total_assets = 0.0
    total_liabilities = 0.0

    for a in accounts:
        atype = a.account_type
        bal = float(a.balance)
        if atype not in type_breakdown:
            type_breakdown[atype] = {"type": atype, "total": 0.0, "count": 0, "accounts": []}
        type_breakdown[atype]["total"] += bal
        type_breakdown[atype]["count"] += 1
        type_breakdown[atype]["accounts"].append(_account_json(a))

        # Credit accounts are liabilities (negative contribution to net worth)
        if atype == AccountType.CREDIT.value:
            total_liabilities += abs(bal)
        else:
            total_assets += bal

    total_balance = sum(float(a.balance) for a in accounts)
    net_worth = total_assets - total_liabilities

    logger.info("Accounts overview user=%s total_accounts=%s net_worth=%s", uid, len(accounts), net_worth)
    return jsonify(
        total_balance=total_balance,
        net_worth=net_worth,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        account_count=len(accounts),
        type_breakdown=list(type_breakdown.values()),
    )
