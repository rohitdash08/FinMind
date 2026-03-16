"""Savings goals CRUD + contribution endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import SavingsContribution, SavingsGoal

bp = Blueprint("goals", __name__)


def _goal_json(g: SavingsGoal) -> dict:
    progress = (
        round(float(g.current_amount) / float(g.target_amount) * 100, 2)
        if float(g.target_amount) > 0
        else 0.0
    )
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "achieved": g.achieved,
        "progress_pct": progress,
        "created_at": g.created_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_goals():
    """List all savings goals for the authenticated user."""
    uid = int(get_jwt_identity())
    goals = (
        SavingsGoal.query.filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return jsonify([_goal_json(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    """Create a new savings goal."""
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    target = data.get("target_amount")
    if target is None or float(target) <= 0:
        return jsonify(error="target_amount must be positive"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=float(target),
        currency=data.get("currency", "INR"),
        deadline=data.get("deadline"),
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(_goal_json(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    """Get a specific savings goal with its contributions."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    contributions = (
        SavingsContribution.query.filter_by(goal_id=goal_id)
        .order_by(SavingsContribution.created_at.desc())
        .all()
    )
    result = _goal_json(goal)
    result["contributions"] = [
        {
            "id": c.id,
            "amount": float(c.amount),
            "notes": c.notes,
            "created_at": c.created_at.isoformat(),
        }
        for c in contributions
    ]
    return jsonify(result)


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    """Update a savings goal (name, target_amount, deadline)."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    data = request.get_json(force=True)
    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        target = float(data["target_amount"])
        if target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = target
        # Recalculate achieved status
        goal.achieved = float(goal.current_amount) >= target
    if "deadline" in data:
        goal.deadline = data["deadline"]

    db.session.commit()
    return jsonify(_goal_json(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    """Delete a savings goal and all its contributions."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    SavingsContribution.query.filter_by(goal_id=goal_id).delete()
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="goal deleted"), 200


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    """Add a contribution to a savings goal."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    data = request.get_json(force=True)
    amount = data.get("amount")
    if amount is None or float(amount) <= 0:
        return jsonify(error="amount must be positive"), 400

    contribution = SavingsContribution(
        goal_id=goal_id,
        amount=float(amount),
        notes=data.get("notes"),
    )
    db.session.add(contribution)

    goal.current_amount = float(goal.current_amount) + float(amount)
    if float(goal.current_amount) >= float(goal.target_amount):
        goal.achieved = True

    db.session.commit()

    result = _goal_json(goal)
    result["contribution"] = {
        "id": contribution.id,
        "amount": float(contribution.amount),
        "notes": contribution.notes,
        "created_at": contribution.created_at.isoformat(),
    }
    # Include milestone info
    result["milestone_reached"] = goal.achieved
    return jsonify(result), 201
