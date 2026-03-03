"""Routes for savings goal tracking & milestones."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.savings import create_goal, list_goals, get_goal, delete_goal, deposit

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("/")
@jwt_required()
def index():
    uid = int(get_jwt_identity())
    return jsonify(list_goals(uid))


@bp.post("/")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    target = data.get("target_amount")
    if not name or target is None:
        return jsonify(error="name and target_amount are required"), 400
    try:
        target = float(target)
    except (TypeError, ValueError):
        return jsonify(error="target_amount must be a number"), 400
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400
    currency = (data.get("currency") or "INR").upper()
    target_date = data.get("target_date")  # ISO string or None
    goal = create_goal(uid, name, target, currency, target_date)
    logger.info("Savings goal created user=%s name=%s", uid, name)
    return jsonify(goal), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def show(goal_id: int):
    uid = int(get_jwt_identity())
    goal = get_goal(uid, goal_id)
    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(goal)


@bp.delete("/<int:goal_id>")
@jwt_required()
def destroy(goal_id: int):
    uid = int(get_jwt_identity())
    if delete_goal(uid, goal_id):
        return jsonify(message="deleted"), 200
    return jsonify(error="not found"), 404


@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def make_deposit(goal_id: int):
    """Record a deposit toward a savings goal."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    if amount is None:
        return jsonify(error="amount is required"), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify(error="amount must be a number"), 400
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400
    notes = (data.get("notes") or "").strip()
    result = deposit(uid, goal_id, amount, notes)
    if result is None:
        return jsonify(error="goal not found"), 404
    return jsonify(result)
