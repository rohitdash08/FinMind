"""Financial accounts endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import accounts as account_service

bp = Blueprint("accounts", __name__)


@bp.get("/")
@jwt_required()
def list_accounts():
    user_id = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    items = account_service.get_accounts(user_id, active_only=not include_inactive)
    return jsonify([account_service.serialize_account(a) for a in items]), 200


@bp.post("/")
@jwt_required()
def create_account():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("name") or not data.get("account_type"):
        return jsonify(error="name and account_type are required"), 400

    account, error = account_service.create_account(
        user_id=user_id,
        name=data["name"],
        account_type=data["account_type"],
        currency=data.get("currency", "INR"),
        balance=data.get("balance", 0),
        color=data.get("color"),
    )
    if error:
        return jsonify(error=error), 400

    return jsonify(account_service.serialize_account(account)), 201


@bp.get("/overview")
@jwt_required()
def get_overview():
    user_id = int(get_jwt_identity())
    overview = account_service.get_overview(user_id)
    return jsonify(overview), 200


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    user_id = int(get_jwt_identity())
    account = account_service.get_account(account_id, user_id)
    if not account:
        return jsonify(error="Account not found"), 404
    return jsonify(account_service.serialize_account(account)), 200


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    account, error = account_service.update_account(account_id, user_id, **data)
    if error:
        status_code = 404 if "not found" in error.lower() else 400
        return jsonify(error=error), status_code
    return jsonify(account_service.serialize_account(account)), 200


@bp.delete("/<int:account_id>")
@jwt_required()
def deactivate_account(account_id):
    user_id = int(get_jwt_identity())
    success = account_service.delete_account(account_id, user_id)
    if not success:
        return jsonify(error="Account not found"), 404
    return jsonify(message="Account deactivated"), 200
