"""Multi-account financial overview routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import accounts as accounts_service

bp = Blueprint("accounts", __name__)


@bp.route("", methods=["POST"])
@jwt_required()
def create_account():
    """Create a new financial account."""
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}

    name = body.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400

    account_type = body.get("account_type", "checking")
    valid_types = ("checking", "savings", "credit_card", "investment", "cash")
    if account_type not in valid_types:
        return jsonify({"error": f"account_type must be one of {valid_types}"}), 400

    try:
        balance = float(body.get("balance", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "balance must be a number"}), 400

    data = accounts_service.create_account(
        user_id=user_id,
        name=name,
        account_type=account_type,
        institution=body.get("institution"),
        balance=balance,
        currency=body.get("currency", "INR"),
    )
    return jsonify(data), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_accounts():
    """List all financial accounts."""
    user_id = get_jwt_identity()
    active_only = request.args.get("active_only", "true").lower() == "true"
    data = accounts_service.list_accounts(user_id, active_only=active_only)
    return jsonify(data), 200


@bp.route("/overview", methods=["GET"])
@jwt_required()
def get_overview():
    """Multi-account dashboard overview."""
    user_id = get_jwt_identity()
    data = accounts_service.get_overview(user_id)
    return jsonify(data), 200


@bp.route("/<int:account_id>", methods=["GET"])
@jwt_required()
def get_account(account_id):
    """Get a single account with recent transactions."""
    user_id = get_jwt_identity()
    data = accounts_service.get_account(account_id, user_id)
    return jsonify(data), 200


@bp.route("/<int:account_id>", methods=["PATCH"])
@jwt_required()
def update_account(account_id):
    """Update account details."""
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    data = accounts_service.update_account(account_id, user_id, **body)
    return jsonify(data), 200


@bp.route("/<int:account_id>", methods=["DELETE"])
@jwt_required()
def delete_account(account_id):
    """Deactivate (soft-delete) an account."""
    user_id = get_jwt_identity()
    data = accounts_service.deactivate_account(account_id, user_id)
    return jsonify(data), 200


@bp.route("/<int:account_id>/transactions", methods=["POST"])
@jwt_required()
def add_transaction(account_id):
    """Add a transaction to an account."""
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}

    amount = body.get("amount")
    if amount is None:
        return jsonify({"error": "amount is required"}), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400

    data = accounts_service.add_transaction(
        account_id=account_id,
        user_id=user_id,
        amount=amount,
        description=body.get("description"),
        category=body.get("category"),
    )
    return jsonify(data), 201


@bp.route("/<int:account_id>/transactions", methods=["GET"])
@jwt_required()
def list_transactions(account_id):
    """List transactions for an account."""
    user_id = get_jwt_identity()
    limit = request.args.get("limit", 20, type=int)
    data = accounts_service.list_transactions(account_id, user_id, limit=limit)
    return jsonify(data), 200
