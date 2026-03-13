from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Goal, GoalMilestone
from datetime import datetime

bp = Blueprint("goals", __name__)


@bp.route("", methods=["GET"])
@jwt_required()
def get_goals():
    uid = int(get_jwt_identity())
    goals = Goal.query.filter_by(user_id=uid).all()
    result = []
    for g in goals:
        milestones = GoalMilestone.query.filter_by(goal_id=g.id).all()
        result.append(
            {
                "id": g.id,
                "name": g.name,
                "target_amount": float(g.target_amount),
                "current_amount": float(g.current_amount),
                "currency": g.currency,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "created_at": g.created_at.isoformat(),
                "milestones": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "target_amount": float(m.target_amount),
                        "achieved": m.achieved,
                    }
                    for m in milestones
                ],
            }
        )
    return jsonify(result), 200


@bp.route("", methods=["POST"])
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.json
    try:
        deadline = (
            datetime.strptime(data["deadline"], "%Y-%m-%d").date()
            if data.get("deadline")
            else None
        )
    except ValueError:
        return jsonify({"error": "Invalid date format, use YYYY-MM-DD"}), 400

    new_goal = Goal(
        user_id=uid,
        name=data["name"],
        target_amount=data["target_amount"],
        current_amount=data.get("current_amount", 0.0),
        currency=data.get("currency", "INR"),
        deadline=deadline,
    )
    db.session.add(new_goal)
    db.session.commit()

    if "milestones" in data:
        for m in data["milestones"]:
            new_ms = GoalMilestone(
                goal_id=new_goal.id,
                name=m["name"],
                target_amount=m["target_amount"],
                achieved=m.get("achieved", False),
            )
            db.session.add(new_ms)
        db.session.commit()

    return jsonify({"message": "Goal created successfully", "id": new_goal.id}), 201


@bp.route("/<int:goal_id>", methods=["PUT"])
@jwt_required()
def update_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify({"error": "Goal not found"}), 404

    data = request.json
    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        goal.target_amount = data["target_amount"]
    if "current_amount" in data:
        goal.current_amount = data["current_amount"]
    if "deadline" in data:
        try:
            goal.deadline = (
                datetime.strptime(data["deadline"], "%Y-%m-%d").date()
                if data["deadline"]
                else None
            )
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400

    db.session.commit()
    return jsonify({"message": "Goal updated successfully"}), 200


@bp.route("/<int:goal_id>", methods=["DELETE"])
@jwt_required()
def delete_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = Goal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify({"message": "Goal deleted successfully"}), 200
