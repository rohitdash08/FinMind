"""Expense splitting & shared costs API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.expense_splitting import (
    create_group, get_groups, get_group, delete_group,
    add_expense, get_balances, calculate_settlements,
)
import logging

bp = Blueprint("splitting", __name__)
logger = logging.getLogger("finmind.splitting")


@bp.get("/groups")
@jwt_required()
def list_groups():
    uid = int(get_jwt_identity())
    return jsonify(get_groups(uid))


@bp.post("/groups")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or not isinstance(data.get("members"), list):
        return jsonify({"error": "name and members array are required"}), 400
    try:
        result = create_group(uid, data["name"], data["members"])
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/groups/<int:group_id>")
@jwt_required()
def get_one(group_id):
    uid = int(get_jwt_identity())
    g = get_group(uid, group_id)
    if not g:
        return jsonify({"error": "Group not found"}), 404
    return jsonify(g)


@bp.delete("/groups/<int:group_id>")
@jwt_required()
def remove(group_id):
    uid = int(get_jwt_identity())
    if delete_group(uid, group_id):
        return jsonify({"message": "Group deleted"})
    return jsonify({"error": "Group not found"}), 404


@bp.post("/groups/<int:group_id>/expenses")
@jwt_required()
def create_expense(group_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    required = ["description", "amount", "paid_by_id"]
    if not all(data.get(k) for k in required):
        return jsonify({"error": "description, amount, and paid_by_id are required"}), 400
    try:
        result = add_expense(uid, group_id, data["description"], float(data["amount"]),
                             int(data["paid_by_id"]), data.get("split_type", "equal"), data.get("shares"))
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/groups/<int:group_id>/balances")
@jwt_required()
def balances(group_id):
    uid = int(get_jwt_identity())
    try:
        return jsonify(get_balances(uid, group_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.get("/groups/<int:group_id>/settlements")
@jwt_required()
def settlements(group_id):
    uid = int(get_jwt_identity())
    try:
        return jsonify(calculate_settlements(uid, group_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
