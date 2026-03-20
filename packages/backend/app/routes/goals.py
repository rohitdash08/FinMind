"""Routes for savings goal management."""

from datetime import date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.savings_goals import (
    create_goal,
    add_contribution,
    get_goal,
    list_goals,
)

bp = Blueprint("goals", __name__)


@bp.get("/")
@jwt_required()
def index():
    """List all savings goals for the authenticated user."""
    user_id = int(get_jwt_identity())
    status = request.args.get("status")
    goals = list_goals(user_id, status=status)
    return jsonify(goals=goals)


@bp.post("/")
@jwt_required()
def create():
    """Create a new savings goal."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    name = data.get("name")
    target = data.get("target_amount")
    if not name or not target:
        return jsonify(error="name and target_amount required"), 400
    try:
        target = float(target)
    except (TypeError, ValueError):
        return jsonify(error="target_amount must be a number"), 400
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="deadline must be YYYY-MM-DD"), 400

    goal = create_goal(
        user_id=user_id,
        name=name,
        target_amount=target,
        currency=data.get("currency", "INR"),
        description=data.get("description"),
        deadline=deadline,
    )
    return jsonify(goal), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def detail(goal_id: int):
    """Get a single savings goal with milestones."""
    user_id = int(get_jwt_identity())
    goal = get_goal(goal_id, user_id)
    if not goal:
        return jsonify(error="goal not found"), 404
    return jsonify(goal)


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    """Add a contribution to a savings goal."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount:
        return jsonify(error="amount required"), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify(error="amount must be a number"), 400
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400
    try:
        result = add_contribution(goal_id, user_id, amount, notes=data.get("notes"))
    except ValueError as e:
        return jsonify(error=str(e)), 404
    return jsonify(result)
