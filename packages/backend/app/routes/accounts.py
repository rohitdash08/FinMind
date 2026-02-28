from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.accounts import (
    create_account, list_accounts, get_account,
    update_account, delete_account, overview,
)
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    acct_type = data.get("account_type", "").strip()
    if not name or not acct_type:
        return jsonify({"error": "name and account_type are required"}), 400
    try:
        result = create_account(
            uid, name, acct_type,
            currency=data.get("currency", "INR"),
            balance=float(data.get("balance", 0)),
        )
        logger.info("Account created id=%s user=%s", result["id"], uid)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("")
@jwt_required()
def list_all():
    uid = int(get_jwt_identity())
    return jsonify(list_accounts(uid))


@bp.get("/overview")
@jwt_required()
def get_overview():
    uid = int(get_jwt_identity())
    return jsonify(overview(uid))


@bp.get("/<int:aid>")
@jwt_required()
def detail(aid):
    uid = int(get_jwt_identity())
    acct = get_account(uid, aid)
    if not acct:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(acct)


@bp.patch("/<int:aid>")
@jwt_required()
def update(aid):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        result = update_account(uid, aid, **data)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.delete("/<int:aid>")
@jwt_required()
def delete(aid):
    uid = int(get_jwt_identity())
    if delete_account(uid, aid):
        return jsonify({"deleted": True})
    return jsonify({"error": "Account not found"}), 404
