"""Financial goal tracking & milestones API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.financial_goals import (
    create_goal, get_goals, get_goal, update_goal, delete_goal,
    add_contribution, get_contributions, goal_projection,
)
import logging

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")


@bp.get("/")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    return jsonify(get_goals(uid, status))


@bp.post("/")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or not data.get("target_amount"):
        return jsonify({"error": "name and target_amount are required"}), 400
    try:
        result = create_goal(uid, data["name"], float(data["target_amount"]),
                             data.get("deadline"), data.get("category", "savings"))
        logger.info("Goal created user=%s goal=%s", uid, result["id"])
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:goal_id>")
@jwt_required()
def get_one(goal_id):
    uid = int(get_jwt_identity())
    g = get_goal(uid, goal_id)
    if not g:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(g)


@bp.put("/<int:goal_id>")
@jwt_required()
def update(goal_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or 
    result = update_goal(uid, goal_id, **data)
    if not result:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(result)


@bp.delete("/<int:goal_id>")
@jwt_required()
def remove(goal_id):
    uid = int(get_jwt_identity())
    if delete_goal(uid, goal_id):
        return jsonify({"message": "Goal deleted"})
    return jsonify({"error": "Goal not found"}), 404


@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def contribute(goal_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("amount"):
        return jsonify({"error": "amount is required"}), 400
    try:
        result = add_contribution(uid, goal_id, float(data["amount"]), data.get("note", ""))
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id):
    uid = int(get_jwt_identity())
    return jsonify(get_contributions(uid, goal_id))


@bp.get("/<int:goal_id>/projection")
@jwt_required()
def projection(goal_id):
    uid = int(get_jwt_identity())
    try:
        return jsonify(goal_projection(uid, goal_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
