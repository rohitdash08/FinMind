from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.savings import create_goal, add_contribution, get_goal, list_goals

bp = Blueprint("savings", __name__)

@bp.get("/goals")
@jwt_required()
def get_goals():
    return jsonify(list_goals(int(get_jwt_identity())))

@bp.post("/goals")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    d = request.get_json() or {}
    if not d.get("name") or not d.get("target_amount"):
        return jsonify(error="name and target_amount required"), 400
    goal = create_goal(uid, d["name"], float(d["target_amount"]),
                       d.get("currency", "INR"), None)
    return jsonify({"id": goal.id, "name": goal.name}), 201

@bp.get("/goals/<int:goal_id>")
@jwt_required()
def detail(goal_id):
    return jsonify(get_goal(goal_id))

@bp.post("/goals/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id):
    d = request.get_json() or {}
    amount = float(d.get("amount", 0))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400
    return jsonify(add_contribution(goal_id, amount))
