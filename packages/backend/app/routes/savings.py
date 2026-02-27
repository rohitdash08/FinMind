"""Savings goals API endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.savings import create_goal, get_goals, get_goal, contribute, update_goal, delete_goal
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("/")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    return jsonify(get_goals(uid, status))


@bp.post("/")
@jwt_required()
def add_goal():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("name") or not data.get("target_amount"):
        return jsonify({"error": "name and target_amount are required"}), 400
    try:
        goal = create_goal(
            uid, data["name"], data["target_amount"],
            data.get("currency", "INR"), data.get("deadline"),
        )
        logger.info("Goal created user=%s name=%s", uid, data["name"])
        return jsonify(goal), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:goal_id>")
@jwt_required()
def get_one(goal_id):
    uid = int(get_jwt_identity())
    goal = get_goal(uid, goal_id)
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal)


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id):
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("amount"):
        return jsonify({"error": "amount is required"}), 400
    try:
        result = contribute(uid, goal_id, data["amount"])
        if not result:
            return jsonify({"error": "Goal not found or not active"}), 404
        logger.info("Contribution user=%s goal=%s amount=%s", uid, goal_id, data["amount"])
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.put("/<int:goal_id>")
@jwt_required()
def update_one(goal_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    goal = update_goal(uid, goal_id, **data)
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal)


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_one(goal_id):
    uid = int(get_jwt_identity())
    if delete_goal(uid, goal_id):
        return jsonify({"message": "Goal deleted"})
    return jsonify({"error": "Goal not found"}), 404
