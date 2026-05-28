"""Goal-based savings tracking API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

from ..services.savings import (
    create_goal,
    add_contribution,
    get_user_goals,
    get_goals_overview,
    get_goal_contributions,
    withdraw_from_goal,
)
from ..models_savings import SavingsGoal, SavingsMilestone

bp = Blueprint("savings", __name__)


@bp.get("/overview")
@jwt_required()
def savings_overview():
    """Get savings goals dashboard overview."""
    user_id = get_jwt_identity()
    overview = get_goals_overview(user_id)
    return jsonify(overview)


@bp.get("/goals")
@jwt_required()
def list_goals():
    """List all savings goals."""
    user_id = get_jwt_identity()
    include_completed = request.args.get("completed", "false").lower() == "true"
    goals = get_user_goals(user_id, include_completed=include_completed)
    return jsonify([g.to_dict() for g in goals])


@bp.post("/goals")
@jwt_required()
def new_goal():
    """Create a new savings goal."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    required = ["name", "target_amount"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        deadline = None
        if data.get("deadline"):
            deadline = datetime.fromisoformat(data["deadline"])

        goal = create_goal(
            user_id=user_id,
            name=data["name"],
            target_amount=float(data["target_amount"]),
            currency=data.get("currency", "USD"),
            deadline=deadline,
            category=data.get("category", "custom"),
            priority=data.get("priority", "medium"),
            icon=data.get("icon"),
            color=data.get("color"),
            description=data.get("description"),
        )
        return jsonify(goal.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id):
    """Get a specific goal with milestones and recent contributions."""
    user_id = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify({"error": "Goal not found"}), 404

    milestones = goal.milestones.all()
    contributions = get_goal_contributions(goal_id, user_id, limit=20)

    return jsonify({
        **goal.to_dict(),
        "milestones": [m.to_dict() for m in milestones],
        "recent_contributions": [c.to_dict() for c in contributions],
    })


@bp.post("/goals/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id):
    """Add a contribution to a savings goal."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    if "amount" not in data:
        return jsonify({"error": "Missing field: amount"}), 400

    try:
        contribution, new_milestones = add_contribution(
            goal_id=goal_id,
            user_id=user_id,
            amount=float(data["amount"]),
            note=data.get("note"),
        )
        return jsonify({
            "contribution": contribution.to_dict(),
            "new_milestones_reached": [m.to_dict() for m in new_milestones],
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/goals/<int:goal_id>/withdraw")
@jwt_required()
def withdraw(goal_id):
    """Withdraw from a savings goal."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    if "amount" not in data:
        return jsonify({"error": "Missing field: amount"}), 400

    try:
        contribution = withdraw_from_goal(
            goal_id=goal_id,
            user_id=user_id,
            amount=float(data["amount"]),
            note=data.get("note"),
        )
        return jsonify({"withdrawal": contribution.to_dict()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/goals/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id):
    """Get contribution history for a goal."""
    user_id = get_jwt_identity()
    limit = request.args.get("limit", 50, type=int)
    contributions = get_goal_contributions(goal_id, user_id, limit=limit)
    return jsonify([c.to_dict() for c in contributions])


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id):
    """Delete a savings goal."""
    user_id = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify({"error": "Goal not found"}), 404

    db.session.delete(goal)
    db.session.commit()
    return jsonify({"message": "Goal deleted"})
