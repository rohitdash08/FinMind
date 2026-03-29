from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount, AccountType, User
from ..services.cache import cache_delete_patterns, cache_get, cache_set
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_ACCOUNT_TYPES = {t.value for t in AccountType}


def _serialize(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type.value,
        "institution": a.institution,
        "balance": float(a.balance),
        "currency": a.currency,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


def _invalidate_cache(uid: int):
    cache_delete_patterns(
        [f"user:{uid}:accounts*", f"user:{uid}:accounts_overview*"]
    )


def _validate_create(data: dict) -> str | None:
    if not data.get("name") or not str(data["name"]).strip():
        return "name is required"
    if not data.get("account_type"):
        return "account_type is required"
    if data["account_type"] not in VALID_ACCOUNT_TYPES:
        return f"account_type must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"
    if "balance" in data:
        try:
            Decimal(str(data["balance"]))
        except (InvalidOperation, TypeError, ValueError):
            return "balance must be a valid number"
    return None


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    show_inactive = request.args.get("include_inactive", "").lower() == "true"

    q = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not show_inactive:
        q = q.filter_by(is_active=True)
    items = q.order_by(FinancialAccount.account_type, FinancialAccount.name).all()

    logger.info("List accounts user=%s count=%s", uid, len(items))
    return jsonify([_serialize(a) for a in items])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    err = _validate_create(data)
    if err:
        return jsonify(error=err), 400

    account = FinancialAccount(
        user_id=uid,
        name=str(data["name"]).strip(),
        account_type=AccountType(data["account_type"]),
        institution=str(data.get("institution", "")).strip() or None,
        balance=Decimal(str(data.get("balance", 0))),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account id=%s user=%s name=%s", account.id, uid, account.name)
    _invalidate_cache(uid)
    return jsonify(_serialize(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_serialize(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        account.name = name

    if "account_type" in data:
        if data["account_type"] not in VALID_ACCOUNT_TYPES:
            return jsonify(error=f"account_type must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"), 400
        account.account_type = AccountType(data["account_type"])

    if "institution" in data:
        account.institution = str(data["institution"]).strip() or None

    if "balance" in data:
        try:
            account.balance = Decimal(str(data["balance"]))
        except (InvalidOperation, TypeError, ValueError):
            return jsonify(error="balance must be a valid number"), 400

    if "currency" in data:
        account.currency = data["currency"]

    if "is_active" in data:
        account.is_active = bool(data["is_active"])

    db.session.commit()
    logger.info("Updated account id=%s user=%s", account.id, uid)
    _invalidate_cache(uid)
    return jsonify(_serialize(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(account)
    db.session.commit()
    logger.info("Deleted account id=%s user=%s", account.id, uid)
    _invalidate_cache(uid)
    return jsonify(message="deleted")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())

    cache_key = f"user:{uid}:accounts_overview"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .all()
    )

    total_balance = float(sum(a.balance for a in accounts))

    # Group by type
    by_type: dict[str, dict] = {}
    for a in accounts:
        t = a.account_type.value
        if t not in by_type:
            by_type[t] = {"type": t, "count": 0, "total_balance": 0.0, "accounts": []}
        by_type[t]["count"] += 1
        by_type[t]["total_balance"] += float(a.balance)
        by_type[t]["accounts"].append(_serialize(a))

    # Group by currency
    by_currency: dict[str, float] = {}
    for a in accounts:
        by_currency[a.currency] = by_currency.get(a.currency, 0.0) + float(a.balance)

    # Group by institution
    by_institution: dict[str, dict] = {}
    for a in accounts:
        inst = a.institution or "Other"
        if inst not in by_institution:
            by_institution[inst] = {"institution": inst, "count": 0, "total_balance": 0.0}
        by_institution[inst]["count"] += 1
        by_institution[inst]["total_balance"] += float(a.balance)

    result = {
        "total_accounts": len(accounts),
        "total_balance": total_balance,
        "by_type": list(by_type.values()),
        "by_currency": [
            {"currency": c, "balance": b} for c, b in sorted(by_currency.items())
        ],
        "by_institution": list(by_institution.values()),
    }

    cache_set(cache_key, result, ttl=300)
    logger.info("Overview user=%s accounts=%s total=%.2f", uid, len(accounts), total_balance)
    return jsonify(result)
