"""Routes for multi-account management."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.accounts import account_service

bp = Blueprint("accounts", __name__)


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    return jsonify(account_service.list_accounts(uid))


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    account, error = account_service.create_account(uid, data)
    if error:
        return jsonify(error=error), 400
    return jsonify(account_service._account_dict(account)), 201


@bp.get("/summary")
@jwt_required()
def get_summary():
    uid = int(get_jwt_identity())
    return jsonify(account_service.get_summary(uid))


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    account = account_service.get_account(uid, account_id)
    if not account:
        return jsonify(error="not found"), 404
    return jsonify(account_service._account_dict(account))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    account, error = account_service.update_account(uid, account_id, data)
    if error:
        status = 404 if error == "not found" else 400
        return jsonify(error=error), status
    return jsonify(account_service._account_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    ok, error = account_service.delete_account(uid, account_id)
    if not ok:
        return jsonify(error=error), 404
    return jsonify(message="deleted")
