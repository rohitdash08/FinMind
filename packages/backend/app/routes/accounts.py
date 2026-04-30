from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.accounts import (
    account_to_dict,
    create_account,
    get_account,
    get_account_overview,
    get_accounts,
    recalculate_balance,
    soft_delete_account,
    update_account,
)
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = get_accounts(uid)
    return jsonify(items)


@bp.get("/overview")
@jwt_required()
def account_overview():
    uid = int(get_jwt_identity())
    overview = get_account_overview(uid)
    return jsonify(overview)


@bp.get("/<int:account_id>")
@jwt_required()
def get_account_detail(account_id: int):
    uid = int(get_jwt_identity())
    account = get_account(uid, account_id)
    if not account:
        return jsonify(error="not found"), 404
    data = account_to_dict(account)
    return jsonify(data)


@bp.post("")
@jwt_required()
def create_account_route():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    data["name"] = name
    account = create_account(uid, data)
    return jsonify(account_to_dict(account)), 201


@bp.put("/<int:account_id>")
@jwt_required()
def update_account_route(account_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    account = update_account(uid, account_id, data)
    if not account:
        return jsonify(error="not found"), 404
    return jsonify(account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account_route(account_id: int):
    uid = int(get_jwt_identity())
    success = soft_delete_account(uid, account_id)
    if not success:
        return jsonify(error="not found"), 404
    return jsonify(message="deleted")


@bp.post("/<int:account_id>/recalculate")
@jwt_required()
def recalculate_account_balance(account_id: int):
    uid = int(get_jwt_identity())
    account = get_account(uid, account_id)
    if not account:
        return jsonify(error="not found"), 404
    new_balance = recalculate_balance(account_id)
    return jsonify(balance=new_balance)
