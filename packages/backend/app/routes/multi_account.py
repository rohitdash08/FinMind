from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.multi_account import create_account, get_overview, update_balance

bp = Blueprint("accounts", __name__)

@bp.get("/overview")
@jwt_required()
def overview():
    return jsonify(get_overview(int(get_jwt_identity())))

@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    d = request.get_json() or {}
    if not d.get("name"):
        return jsonify(error="name required"), 400
    acct = create_account(uid, d["name"], d.get("account_type","checking"),
                          d.get("currency","INR"), float(d.get("balance",0)),
                          d.get("institution"))
    return jsonify({"id": acct.id, "name": acct.name}), 201

@bp.patch("/<int:account_id>/balance")
@jwt_required()
def patch_balance(account_id):
    d = request.get_json() or {}
    acct = update_balance(account_id, float(d.get("balance", 0)))
    return jsonify({"id": acct.id, "balance": float(acct.balance)})
