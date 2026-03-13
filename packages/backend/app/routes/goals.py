from flask import Blueprint, jsonify, request
from app.models import Goal, GoalMilestone, db
from app.auth import token_required
from datetime import datetime

bp = Blueprint("goals", __name__)


@bp.route("", methods=["GET"])
@token_required
def get_goals(current_user):
    goals = Goal.query.filter_by(user_id=current_user.id).all()
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
@token_required
def create_goal(current_user):
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
        user_id=current_user.id,
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
@token_required
def update_goal(current_user, goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
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
@token_required
def delete_goal(current_user, goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify({"message": "Goal deleted successfully"}), 200
