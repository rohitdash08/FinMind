"""Financial accounts routes (issue #132).

GET    /accounts              list all accounts
POST   /accounts              create account
GET    /accounts/overview     net-worth summary across all accounts
GET    /accounts/<id>         get one account
PATCH  /accounts/<id>         update account
DELETE /accounts/<id>         delete account  (204)
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.accounts import (
    account_to_dict,
    create_account,
    delete_account,
    get_account,
    get_accounts,
    get_overview,
    update_account,
)

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts.routes")


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    return jsonify([account_to_dict(a) for a in get_accounts(uid)])


@bp.post("")
@jwt_required()
def create_account_endpoint():
    uid = int(get_jwt_identity())
    acc, err = create_account(uid, request.get_json() or {})
    if err:
        return jsonify(error=err), 400
    return jsonify(account_to_dict(acc)), 201


@bp.get("/overview")
@jwt_required()
def overview():
    uid = int(get_jwt_identity())
    return jsonify(get_overview(uid))


@bp.get("/<int:account_id>")
@jwt_required()
def get_account_endpoint(account_id: int):
    uid = int(get_jwt_identity())
    acc = get_account(uid, account_id)
    if not acc:
        return jsonify(error="not found"), 404
    return jsonify(account_to_dict(acc))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account_endpoint(account_id: int):
    uid = int(get_jwt_identity())
    acc, err = update_account(uid, account_id, request.get_json() or {})
    if err == "not found":
        return jsonify(error=err), 404
    if err:
        return jsonify(error=err), 400
    return jsonify(account_to_dict(acc))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account_endpoint(account_id: int):
    uid = int(get_jwt_identity())
    if not delete_account(uid, account_id):
        return jsonify(error="not found"), 404
    return "", 204
