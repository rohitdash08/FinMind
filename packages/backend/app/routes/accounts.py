from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Account, AccountType, User

bp = Blueprint("accounts", __name__)


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid)
        .order_by(Account.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    raw_type = str(data.get("type") or "").upper().strip()
    if raw_type not in {t.value for t in AccountType}:
        return jsonify(
            error=f"invalid type, must be one of {', '.join(t.value for t in AccountType)}"
        ), 400

    balance = _parse_amount(data.get("balance", 0))
    if balance is None:
        return jsonify(error="invalid balance"), 400

    currency = (data.get("currency") or (user.preferred_currency if user else "INR"))[
        :10
    ]
    is_default = bool(data.get("is_default", False))

    account = Account(
        user_id=uid,
        name=name,
        type=AccountType(raw_type),
        balance=balance,
        currency=currency,
        is_default=is_default,
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_account_to_dict(account)), 201


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid)
        .order_by(Account.created_at.desc())
        .all()
    )

    if not accounts:
        return jsonify(
            total_balance=0.0,
            accounts=[],
            asset_allocation=[],
        )

    # Group by currency for total balance
    currency_totals = {}
    for a in accounts:
        c = a.currency
        currency_totals[c] = currency_totals.get(c, Decimal("0")) + (a.balance or Decimal("0"))

    # Build accounts list
    accounts_list = [_account_to_dict(a) for a in accounts]

    # Asset allocation: percentage by account type
    total_balance = sum(currency_totals.values())
    type_totals = {}
    for a in accounts:
        t = a.type.value
        type_totals[t] = type_totals.get(t, Decimal("0")) + (a.balance or Decimal("0"))

    asset_allocation = []
    for t, amount in sorted(type_totals.items()):
        share_pct = round((float(amount) / float(total_balance)) * 100, 2) if total_balance > 0 else 0
        asset_allocation.append(
            {
                "type": t,
                "amount": float(amount),
                "share_pct": share_pct,
            }
        )

    return jsonify(
        total_balance=float(total_balance),
        accounts=accounts_list,
        asset_allocation=asset_allocation,
    )


def _account_to_dict(a: Account) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "type": a.type.value,
        "balance": float(a.balance or 0),
        "currency": a.currency,
        "is_default": a.is_default,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
