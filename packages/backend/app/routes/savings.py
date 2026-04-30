from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import savings as savings_service

bp = Blueprint("savings", __name__)


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = savings_service.get_goals(uid)
    return jsonify(goals)


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = savings_service.get_goal(uid, goal_id)
    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(goal)


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    # deadlineのパース
    deadline_raw = data.get("deadline")
    if deadline_raw:
        try:
            data["deadline"] = date.fromisoformat(deadline_raw)
        except (ValueError, TypeError):
            return jsonify(error="invalid deadline format, expected YYYY-MM-DD"), 400
    else:
        data["deadline"] = None

    try:
        goal = savings_service.create_goal(uid, data)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    return jsonify(goal), 201


@bp.put("/goals/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    # deadlineのパース
    if "deadline" in data:
        deadline_raw = data.get("deadline")
        if deadline_raw:
            try:
                data["deadline"] = date.fromisoformat(deadline_raw)
            except (ValueError, TypeError):
                return jsonify(error="invalid deadline format"), 400
        else:
            data["deadline"] = None

    try:
        goal = savings_service.update_goal(uid, goal_id, data)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(goal)


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    deleted = savings_service.delete_goal(uid, goal_id)
    if not deleted:
        return jsonify(error="not found"), 404
    return jsonify(message="deleted")


@bp.post("/goals/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    note = data.get("note")

    try:
        result = savings_service.add_contribution(uid, goal_id, amount, note)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    if not result:
        return jsonify(error="not found"), 404
    return jsonify(result), 201


@bp.get("/summary")
@jwt_required()
def savings_summary():
    uid = int(get_jwt_identity())
    summary = savings_service.get_savings_summary(uid)
    return jsonify(summary)
