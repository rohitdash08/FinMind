from decimal import Decimal, InvalidOperation
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import AccountType, FinancialAccount

bp = Blueprint("accounts", __name__)


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    q = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_inactive:
        q = q.filter_by(is_active=True)
    accounts = q.order_by(FinancialAccount.created_at.asc()).all()
    return jsonify([_account_to_dict(a) for a in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    account_type = _parse_account_type(data.get("account_type"))
    if account_type is None:
        valid = [t.value for t in AccountType]
        return jsonify(error=f"account_type must be one of {valid}"), 400

    balance = _parse_decimal(data.get("balance", "0"))
    if balance is None:
        return jsonify(error="invalid balance"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        balance=balance,
        currency=(data.get("currency") or "USD")[:10],
        institution=(data.get("institution") or "").strip() or None,
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_owned(account_id, uid)
    if account is None:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account))


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_owned(account_id, uid)
    if account is None:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name

    if "account_type" in data:
        account_type = _parse_account_type(data.get("account_type"))
        if account_type is None:
            valid = [t.value for t in AccountType]
            return jsonify(error=f"account_type must be one of {valid}"), 400
        account.account_type = account_type

    if "balance" in data:
        balance = _parse_decimal(data.get("balance"))
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance

    if "currency" in data:
        account.currency = (data.get("currency") or "USD")[:10]

    if "institution" in data:
        account.institution = (data.get("institution") or "").strip() or None

    if "is_active" in data:
        account.is_active = bool(data.get("is_active"))

    account.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_owned(account_id, uid)
    if account is None:
        return jsonify(error="not found"), 404
    account.is_active = False
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )

    # Totals by currency
    totals_by_currency: dict[str, float] = {}
    # Totals by account type
    by_type: dict[str, dict] = {}

    for a in accounts:
        bal = float(a.balance)
        cur = a.currency
        totals_by_currency[cur] = totals_by_currency.get(cur, 0.0) + bal

        atype = a.account_type.value
        if atype not in by_type:
            by_type[atype] = {"account_type": atype, "count": 0, "balances": {}}
        by_type[atype]["count"] += 1
        by_type[atype]["balances"][cur] = by_type[atype]["balances"].get(cur, 0.0) + bal

    return jsonify(
        {
            "total_accounts": len(accounts),
            "totals_by_currency": totals_by_currency,
            "by_type": list(by_type.values()),
            "accounts": [_account_to_dict(a) for a in accounts],
        }
    )


# --- helpers ---

def _get_owned(account_id: int, uid: int) -> FinancialAccount | None:
    a = db.session.get(FinancialAccount, account_id)
    if a is None or a.user_id != uid or not a.is_active:
        return None
    return a


def _parse_account_type(raw) -> AccountType | None:
    try:
        return AccountType(str(raw or "").lower().strip())
    except ValueError:
        return None


def _parse_decimal(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _account_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type.value,
        "balance": float(a.balance),
        "currency": a.currency,
        "institution": a.institution,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }
