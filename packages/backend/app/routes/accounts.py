from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Account, User
from ..services.cache import cache_delete_patterns

bp = Blueprint("accounts", __name__)


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid)
        .order_by(Account.active.desc(), Account.name.asc())
        .all()
    )
    return jsonify([_account_to_dict(account) for account in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    balance = _parse_amount(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400
    account = Account(
        user_id=uid,
        name=name[:120],
        account_type=str(data.get("account_type") or "checking").strip()[:40],
        balance=balance,
        currency=str(
            data.get("currency") or (user.preferred_currency if user else "INR")
        )[:10],
        active=bool(data.get("active", True)),
    )
    db.session.add(account)
    db.session.commit()
    _invalidate_dashboard(uid)
    return jsonify(_account_to_dict(account)), 201


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(Account, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name[:120]
    if "account_type" in data:
        account.account_type = str(data.get("account_type") or "checking").strip()[:40]
    if "currency" in data:
        account.currency = str(data.get("currency") or "INR")[:10]
    if "balance" in data:
        balance = _parse_amount(data.get("balance"))
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "active" in data:
        account.active = bool(data.get("active"))
    db.session.commit()
    _invalidate_dashboard(uid)
    return jsonify(_account_to_dict(account))


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _account_to_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "balance": float(account.balance),
        "currency": account.currency,
        "active": account.active,
    }


def _invalidate_dashboard(uid: int) -> None:
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
