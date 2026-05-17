"""Savings goals and milestones API endpoints."""

from datetime import datetime, date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, SavingsMilestone, User

savings_goals_bp = Blueprint("savings_goals", __name__, url_prefix="/api/savings-goals")


def _serialize_goal(goal: SavingsGoal) -> dict:
    progress_pct = (
        float(goal.current_amount) / float(goal.target_amount) * 100
        if goal.target_amount and float(goal.target_amount) > 0
        else 0
    )
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "status": goal.status.value,
        "progress_pct": round(progress_pct, 2),
        "milestones": [
            {
                "id": m.id,
                "threshold_pct": m.threshold_pct,
                "label": m.label,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in goal.milestones
        ],
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }


@savings_goals_bp.route("", methods=["POST"])
@jwt_required()
def create_goal():
    """Create a new savings goal with optional milestones."""
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first_or_404()
    data = request.get_json()

    required = ["name", "target_amount"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    target = data["target_amount"]
    if target <= 0:
        return jsonify({"error": "target_amount must be positive"}), 400

    goal = SavingsGoal(
        user_id=user.id,
        name=data["name"][:200],
        target_amount=target,
        current_amount=data.get("current_amount", 0),
        currency=data.get("currency", user.preferred_currency),
        deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
    )

    # Auto-create default milestones at 25%, 50%, 75%, 100%
    milestones_data = data.get("milestones")
    if milestones_data is None:
        milestones_data = [
            {"threshold_pct": 25, "label": "Quarter way"},
            {"threshold_pct": 50, "label": "Halfway there"},
            {"threshold_pct": 75, "label": "Almost there"},
            {"threshold_pct": 100, "label": "Goal reached!"},
        ]

    for m in milestones_data:
        milestone = SavingsMilestone(
            goal=goal,
            threshold_pct=m["threshold_pct"],
            label=m.get("label"),
        )
        db.session.add(milestone)

    db.session.add(goal)
    db.session.commit()

    return jsonify(_serialize_goal(goal)), 201


@savings_goals_bp.route("", methods=["GET"])
@jwt_required()
def list_goals():
    """List all savings goals for the current user."""
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first_or_404()
    status_filter = request.args.get("status")

    query = SavingsGoal.query.filter_by(user_id=user.id)
    if status_filter:
        try:
            status_enum = SavingsGoalStatus(status_filter)
            query = query.filter_by(status=status_enum)
        except ValueError:
            return jsonify({"error": f"Invalid status: {status_filter}"}), 400

    goals = query.order_by(SavingsGoal.created_at.desc()).all()
    return jsonify({"goals": [_serialize_goal(g) for g in goals]})


@savings_goals_bp.route("/<int:goal_id>", methods=["GET"])
@jwt_required()
def get_goal(goal_id: int):
    """Get a specific savings goal."""
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first_or_404()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    return jsonify(_serialize_goal(goal))


@savings_goals_bp.route("/<int:goal_id>", methods=["PATCH"])
@jwt_required()
def update_goal(goal_id: int):
    """Update a savings goal (name, target_amount, deadline, add funds)."""
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first_or_404()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    data = request.get_json()

    if "name" in data:
        goal.name = data["name"][:200]
    if "target_amount" in data:
        if data["target_amount"] <= 0:
            return jsonify({"error": "target_amount must be positive"}), 400
        goal.target_amount = data["target_amount"]
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    if "add_amount" in data:
        goal.current_amount = float(goal.current_amount) + float(data["add_amount"])

    # Check milestone completion
    progress_pct = float(goal.current_amount) / float(goal.target_amount) * 100
    for milestone in goal.milestones:
        if milestone.reached_at is None and progress_pct >= milestone.threshold_pct:
            milestone.reached_at = datetime.utcnow()

    # Auto-complete if 100% reached
    if progress_pct >= 100 and goal.status == SavingsGoalStatus.ACTIVE:
        goal.status = SavingsGoalStatus.COMPLETED

    goal.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_goal(goal))


@savings_goals_bp.route("/<int:goal_id>", methods=["DELETE"])
@jwt_required()
def delete_goal(goal_id: int):
    """Cancel a savings goal."""
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first_or_404()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    goal.status = SavingsGoalStatus.CANCELLED
    goal.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Goal cancelled", "id": goal.id})


@savings_goals_bp.route("/<int:goal_id>/milestones", methods=["POST"])
@jwt_required()
def add_milestone(goal_id: int):
    """Add a milestone to a savings goal."""
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first_or_404()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    data = request.get_json()

    if "threshold_pct" not in data:
        return jsonify({"error": "'threshold_pct' is required"}), 400

    pct = data["threshold_pct"]
    if not (0 < pct <= 100):
        return jsonify({"error": "threshold_pct must be between 1 and 100"}), 400

    progress_pct = float(goal.current_amount) / float(goal.target_amount) * 100
    milestone = SavingsMilestone(
        goal_id=goal.id,
        threshold_pct=pct,
        label=data.get("label"),
        reached_at=datetime.utcnow() if progress_pct >= pct else None,
    )
    db.session.add(milestone)
    db.session.commit()

    return jsonify({
        "id": milestone.id,
        "threshold_pct": milestone.threshold_pct,
        "label": milestone.label,
        "reached_at": milestone.reached_at.isoformat() if milestone.reached_at else None,
    }), 201
