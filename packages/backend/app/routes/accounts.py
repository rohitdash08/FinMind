"""Multi-account management API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.accounts import (
    create_account,
    get_user_accounts,
    get_account_summary,
    transfer_between_accounts,
    update_account_balance,
)
from ..extensions import db
from ..models_accounts import Account

bp = Blueprint("accounts", __name__)


@bp.get("/")
@jwt_required()
def list_accounts():
    """List all accounts for the current user."""
    user_id = get_jwt_identity()
    accounts = get_user_accounts(user_id)
    return jsonify([a.to_dict() for a in accounts])


@bp.get("/summary")
@jwt_required()
def account_summary():
    """Get multi-account financial overview."""
    user_id = get_jwt_identity()
    summary = get_account_summary(user_id)
    return jsonify(summary)


@bp.post("/")
@jwt_required()
def add_account():
    """Create a new financial account."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    required = ["name", "account_type"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        account = create_account(
            user_id=user_id,
            name=data["name"],
            account_type=data["account_type"],
            currency=data.get("currency", "USD"),
            balance=data.get("balance", 0.0),
            credit_limit=data.get("credit_limit"),
            interest_rate=data.get("interest_rate"),
            color=data.get("color"),
            icon=data.get("icon"),
            institution=data.get("institution"),
        )
        return jsonify(account.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    """Update account details."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404

    for field in ["name", "color", "icon", "institution", "is_active"]:
        if field in data:
            setattr(account, field, data[field])

    db.session.commit()
    return jsonify(account.to_dict())


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    """Deactivate an account (soft delete)."""
    user_id = get_jwt_identity()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404

    account.is_active = False
    db.session.commit()
    return jsonify({"message": "Account deactivated"})


@bp.post("/transfer")
@jwt_required()
def transfer():
    """Transfer money between accounts."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    required = ["from_account_id", "to_account_id", "amount"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        transfer = transfer_between_accounts(
            user_id=user_id,
            from_id=data["from_account_id"],
            to_id=data["to_account_id"],
            amount=float(data["amount"]),
            note=data.get("note"),
        )
        return jsonify(transfer.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.put("/<int:account_id>/balance")
@jwt_required()
def sync_balance(account_id):
    """Manually sync account balance."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    if "balance" not in data:
        return jsonify({"error": "Missing field: balance"}), 400

    try:
        account = update_account_balance(
            account_id=account_id,
            user_id=user_id,
            new_balance=float(data["balance"]),
        )
        return jsonify(account.to_dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
