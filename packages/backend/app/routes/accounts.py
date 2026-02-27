"""Multi-account financial overview API endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.accounts import (
    create_account,
    get_accounts,
    get_account,
    update_account,
    delete_account,
    overview,
)
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")


@bp.get("/")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    active_only = request.args.get("active_only", "true").lower() == "true"
    return jsonify(get_accounts(uid, active_only))


@bp.post("/")
@jwt_required()
def add_account():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("name") or not data.get("account_type"):
        return jsonify({"error": "name and account_type are required"}), 400
    try:
        acct = create_account(
            uid,
            data["name"],
            data["account_type"],
            data.get("currency", "INR"),
            data.get("balance", 0),
        )
        logger.info("Account created user=%s name=%s", uid, data["name"])
        return jsonify(acct), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:account_id>")
@jwt_required()
def get_one(account_id):
    uid = int(get_jwt_identity())
    acct = get_account(uid, account_id)
    if not acct:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(acct)


@bp.put("/<int:account_id>")
@jwt_required()
def update_one(account_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        acct = update_account(uid, account_id, **data)
        if not acct:
            return jsonify({"error": "Account not found"}), 404
        logger.info("Account updated user=%s id=%s", uid, account_id)
        return jsonify(acct)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_one(account_id):
    uid = int(get_jwt_identity())
    if delete_account(uid, account_id):
        logger.info("Account deleted user=%s id=%s", uid, account_id)
        return jsonify({"message": "Account deleted"}), 200
    return jsonify({"error": "Account not found"}), 404


@bp.get("/overview")
@jwt_required()
def get_overview():
    uid = int(get_jwt_identity())
    result = overview(uid)
    logger.info("Overview served user=%s accounts=%s", uid, result["total_accounts"])
    return jsonify(result)
