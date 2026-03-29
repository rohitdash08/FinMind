from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    SavingsGoal,
    SavingsGoalCategory,
    SavingsGoalMilestone,
    SavingsGoalContribution,
    User,
)
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")

MILESTONE_PERCENTAGES = [25, 50, 75, 100]


def _create_milestones(goal: SavingsGoal) -> None:
    """Auto-generate milestone records at 25%, 50%, 75%, 100%."""
    for pct in MILESTONE_PERCENTAGES:
        milestone = SavingsGoalMilestone(goal_id=goal.id, percentage=pct)
        db.session.add(milestone)


def _check_milestones(goal: SavingsGoal) -> list[dict]:
    """Check and update milestone status. Returns newly reached milestones."""
    newly_reached = []
    progress = goal.progress_pct
    for milestone in goal.milestones:
        if not milestone.reached and progress >= milestone.percentage:
            milestone.reached = True
            milestone.reached_at = datetime.utcnow()
            newly_reached.append(milestone.to_dict())
    return newly_reached


def _validate_goal_data(data: dict, is_update: bool = False) -> tuple[dict | None, str | None]:
    """Validate goal creation/update data. Returns (parsed_data, error_message)."""
    errors = []

    if not is_update:
        if not data.get("name", "").strip():
            errors.append("name is required")
        if "target_amount" not in data:
            errors.append("target_amount is required")

    parsed = {}

    if "name" in data:
        name = data["name"].strip()
        if not name:
            errors.append("name cannot be empty")
        elif len(name) > 200:
            errors.append("name must be 200 characters or less")
        parsed["name"] = name

    if "target_amount" in data:
        try:
            target = Decimal(str(data["target_amount"]))
            if target <= 0:
                errors.append("target_amount must be positive")
            parsed["target_amount"] = target
        except (InvalidOperation, ValueError, TypeError):
            errors.append("target_amount must be a valid number")

    if "deadline" in data and data["deadline"]:
        try:
            parsed["deadline"] = date.fromisoformat(data["deadline"])
        except (ValueError, TypeError):
            errors.append("deadline must be a valid ISO date (YYYY-MM-DD)")

    if "category" in data:
        try:
            parsed["category"] = SavingsGoalCategory(data["category"])
        except ValueError:
            valid = [c.value for c in SavingsGoalCategory]
            errors.append(f"category must be one of: {', '.join(valid)}")

    if errors:
        return None, "; ".join(errors)
    return parsed, None


@bp.get("")
@jwt_required()
def list_goals():
    """List all savings goals for the authenticated user."""
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("List savings goals user=%s count=%s", uid, len(goals))

    result = []
    for g in goals:
        d = g.to_dict()
        # Add time-based projection
        if g.deadline and float(g.current_amount) < float(g.target_amount):
            days_left = (g.deadline - date.today()).days
            remaining = float(g.target_amount) - float(g.current_amount)
            d["days_remaining"] = max(days_left, 0)
            d["daily_target"] = round(remaining / max(days_left, 1), 2)
            d["monthly_target"] = round(remaining / max(days_left / 30, 0.1), 2)
            d["on_track"] = days_left > 0
        else:
            d["days_remaining"] = None
            d["daily_target"] = None
            d["monthly_target"] = None
            d["on_track"] = g.progress_pct >= 100
        result.append(d)

    return jsonify(result)


@bp.post("")
@jwt_required()
def create_goal():
    """Create a new savings goal with auto-generated milestones."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    parsed, error = _validate_goal_data(data)
    if error:
        return jsonify(error=error), 400

    goal = SavingsGoal(
        user_id=uid,
        name=parsed["name"],
        target_amount=parsed["target_amount"],
        current_amount=Decimal(str(data.get("current_amount", 0))),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=parsed.get("deadline"),
        category=parsed.get("category", SavingsGoalCategory.OTHER),
    )
    db.session.add(goal)
    db.session.flush()  # get goal.id

    _create_milestones(goal)
    # Check if initial current_amount already hits milestones
    _check_milestones(goal)

    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, goal.name)
    return jsonify(goal.to_dict()), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    """Get a single savings goal with full details."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    d = goal.to_dict()
    # Add projections
    if goal.deadline and float(goal.current_amount) < float(goal.target_amount):
        days_left = (goal.deadline - date.today()).days
        remaining = float(goal.target_amount) - float(goal.current_amount)
        d["days_remaining"] = max(days_left, 0)
        d["daily_target"] = round(remaining / max(days_left, 1), 2)
        d["monthly_target"] = round(remaining / max(days_left / 30, 0.1), 2)
        d["on_track"] = days_left > 0
    else:
        d["days_remaining"] = None
        d["daily_target"] = None
        d["monthly_target"] = None
        d["on_track"] = goal.progress_pct >= 100

    # Include contribution history
    contributions = (
        db.session.query(SavingsGoalContribution)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsGoalContribution.created_at.desc())
        .all()
    )
    d["contributions"] = [c.to_dict() for c in contributions]

    return jsonify(d)


@bp.route("/<int:goal_id>", methods=["PUT", "PATCH"])
@jwt_required()
def update_goal(goal_id: int):
    """Update a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    parsed, error = _validate_goal_data(data, is_update=True)
    if error:
        return jsonify(error=error), 400

    if "name" in parsed:
        goal.name = parsed["name"]
    if "target_amount" in parsed:
        goal.target_amount = parsed["target_amount"]
        # Re-check milestones since target changed
        _check_milestones(goal)
    if "deadline" in parsed:
        goal.deadline = parsed["deadline"]
    elif "deadline" in data and data["deadline"] is None:
        goal.deadline = None
    if "category" in parsed:
        goal.category = parsed["category"]
    if "currency" in data:
        goal.currency = data["currency"]

    goal.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return jsonify(goal.to_dict())


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    """Delete a savings goal and all related data."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal.id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    """Add a contribution toward a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    try:
        amount = Decimal(str(data.get("amount", 0)))
        if amount <= 0:
            return jsonify(error="amount must be positive"), 400
    except (InvalidOperation, ValueError, TypeError):
        return jsonify(error="amount must be a valid number"), 400

    # Create contribution record
    contribution = SavingsGoalContribution(
        goal_id=goal.id,
        amount=amount,
        note=data.get("note", "").strip()[:500] if data.get("note") else None,
    )
    db.session.add(contribution)

    # Update goal current amount
    goal.current_amount = Decimal(str(goal.current_amount)) + amount
    goal.updated_at = datetime.utcnow()

    # Check milestones
    newly_reached = _check_milestones(goal)

    db.session.commit()
    logger.info(
        "Contribution to goal id=%s user=%s amount=%s new_total=%s",
        goal.id,
        uid,
        amount,
        goal.current_amount,
    )

    return jsonify(
        {
            "goal": goal.to_dict(),
            "contribution": contribution.to_dict(),
            "newly_reached_milestones": newly_reached,
        }
    )


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def get_milestones(goal_id: int):
    """Get milestones for a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestones = (
        db.session.query(SavingsGoalMilestone)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsGoalMilestone.percentage)
        .all()
    )
    return jsonify([m.to_dict() for m in milestones])
