"""REST API endpoints for savings goals and milestones."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.savings_goals import (
    list_goals,
    get_goal,
    create_goal,
    update_goal,
    delete_goal,
    add_contribution,
    withdraw,
)
from ..models import User
from ..extensions import db
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("")
@jwt_required()
def list_savings_goals():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    goals = list_goals(uid, status=status)
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
    return jsonify(goals)


@bp.get("/<int:goal_id>")
@jwt_required()
def get_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = get_goal(uid, goal_id)
    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(goal)


@bp.post("")
@jwt_required()
def create_savings_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = data.get("name")
    target_amount = data.get("target_amount")
    if not name or not target_amount:
        return jsonify(error="name and target_amount are required"), 400

    if float(target_amount) <= 0:
        return jsonify(error="target_amount must be positive"), 400

    user = db.session.get(User, uid)
    currency = data.get("currency") or (
        user.preferred_currency if user else "INR"
    )

    goal = create_goal(
        user_id=uid,
        name=name,
        target_amount=float(target_amount),
        currency=currency,
        target_date=data.get("target_date"),
        custom_milestones=data.get("milestones"),
    )
    logger.info("Created savings goal id=%s user=%s name=%s", goal["id"], uid, name)
    return jsonify(goal), 201


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    if "target_amount" in data and float(data["target_amount"]) <= 0:
        return jsonify(error="target_amount must be positive"), 400

    goal = update_goal(
        user_id=uid,
        goal_id=goal_id,
        name=data.get("name"),
        target_amount=float(data["target_amount"]) if "target_amount" in data else None,
        currency=data.get("currency"),
        target_date=data.get("target_date"),
    )
    if not goal:
        return jsonify(error="not found or not active"), 404
    logger.info("Updated savings goal id=%s user=%s", goal_id, uid)
    return jsonify(goal)


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    ok = delete_goal(uid, goal_id)
    if not ok:
        return jsonify(error="not found"), 404
    logger.info("Cancelled savings goal id=%s user=%s", goal_id, uid)
    return jsonify(message="cancelled")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute_to_goal(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify(error="amount must be positive"), 400

    result = add_contribution(uid, goal_id, float(amount))
    if not result:
        return jsonify(error="not found or not active"), 404
    logger.info(
        "Contribution to goal id=%s user=%s amount=%s", goal_id, uid, amount
    )
    return jsonify(result)


@bp.post("/<int:goal_id>/withdraw")
@jwt_required()
def withdraw_from_goal(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify(error="amount must be positive"), 400

    result = withdraw(uid, goal_id, float(amount))
    if not result:
        return jsonify(error="not found, not active, or insufficient funds"), 404
    logger.info(
        "Withdrawal from goal id=%s user=%s amount=%s", goal_id, uid, amount
    )
    return jsonify(result)
