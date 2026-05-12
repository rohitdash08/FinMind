"""Financial accounts routes for multi-account overview."""

from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import FinancialAccount

bp = Blueprint("accounts", __name__)

VALID_ACCOUNT_TYPES = {"checking", "savings", "credit", "investment", "cash", "other"}


@bp.get("/")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .order_by(FinancialAccount.created_at.desc())
        .all()
    )
    return jsonify(accounts=[_serialize(a) for a in accounts])


@bp.get("/overview")
@jwt_required()
def overview():
    """Aggregated multi-account financial overview."""
    uid = int(get_jwt_identity())
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, is_active=True)
        .all()
    )

    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    by_type = {}

    for a in accounts:
        bal = Decimal(str(a.balance))
        if a.account_type == "credit":
            total_liabilities += abs(bal)
        else:
            total_assets += bal

        by_type.setdefault(a.account_type, Decimal("0"))
        by_type[a.account_type] += bal

    return jsonify(
        total_assets=float(total_assets),
        total_liabilities=float(total_liabilities),
        net_worth=float(total_assets - total_liabilities),
        account_count=len(accounts),
        by_type={k: float(v) for k, v in by_type.items()},
        accounts=[_serialize(a) for a in accounts],
    )


@bp.post("/")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = data.get("name")
    account_type = data.get("account_type", "checking")
    if not name:
        return jsonify(error="name required"), 400
    if account_type not in VALID_ACCOUNT_TYPES:
        return jsonify(error=f"invalid account_type, must be one of: {sorted(VALID_ACCOUNT_TYPES)}"), 400

    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=data.get("currency", "INR"),
        balance=Decimal(str(data.get("balance", 0))),
        institution=data.get("institution"),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(account=_serialize(account)), 201


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.query(FinancialAccount).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        account.name = data["name"]
    if "balance" in data:
        account.balance = Decimal(str(data["balance"]))
    if "institution" in data:
        account.institution = data["institution"]
    if "is_active" in data:
        account.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify(account=_serialize(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    uid = int(get_jwt_identity())
    account = db.session.query(FinancialAccount).filter_by(id=account_id, user_id=uid).first()
    if not account:
        return jsonify(error="not found"), 404
    account.is_active = False
    db.session.commit()
    return jsonify(message="account deactivated"), 200


def _serialize(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "institution": a.institution,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
    }
