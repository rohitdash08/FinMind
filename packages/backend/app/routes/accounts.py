"""Routes for multi-account financial management."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.accounts import (
    create_account,
    delete_account,
    get_account,
    list_accounts,
    multi_account_overview,
)

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

VALID_TYPES = {"checking", "savings", "credit", "investment", "cash", "other"}


@bp.get("/")
@jwt_required()
def index():
    uid = int(get_jwt_identity())
    return jsonify(list_accounts(uid))


@bp.post("/")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    acct_type = (data.get("type") or "checking").strip().lower()
    if acct_type not in VALID_TYPES:
        return jsonify(error=f"type must be one of {sorted(VALID_TYPES)}"), 400
    currency = (data.get("currency") or "INR").strip().upper()
    acct = create_account(uid, name, acct_type, currency)
    logger.info("Account created user=%s name=%s", uid, name)
    return jsonify(acct), 201


@bp.get("/<int:account_id>")
@jwt_required()
def show(account_id: int):
    uid = int(get_jwt_identity())
    acct = get_account(uid, account_id)
    if not acct:
        return jsonify(error="not found"), 404
    return jsonify(acct)


@bp.delete("/<int:account_id>")
@jwt_required()
def destroy(account_id: int):
    uid = int(get_jwt_identity())
    if delete_account(uid, account_id):
        return jsonify(message="deleted"), 200
    return jsonify(error="not found"), 404


@bp.get("/overview")
@jwt_required()
def overview():
    """Multi-account financial overview — balances across all accounts."""
    uid = int(get_jwt_identity())
    return jsonify(multi_account_overview(uid))
