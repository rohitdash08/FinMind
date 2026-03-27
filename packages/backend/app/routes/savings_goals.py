"""
API routes for savings goals and milestones.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import GoalContribution, GoalStatus, SavingsGoal, User

bp = Blueprint("savings_goals", __name__)


@bp.get("")
@jwt_required()
def list_goals():
    """List all savings goals for the current user."""
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")

    q = db.session.query(SavingsGoal).filter_by(user_id=uid)

    if status_filter:
        try:
            q = q.filter_by(status=GoalStatus(status_filter.upper()))
        except ValueError:
            pass  # Ignore invalid status filter

    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    """Create a new savings goal."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="valid target_amount is required"), 400

    target_date = None
    if data.get("target_date"):
        try:
            target_date = date.fromisoformat(data.get("target_date"))
        except ValueError:
            return jsonify(error="invalid target_date format (use YYYY-MM-DD)"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        current_amount=Decimal("0"),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        target_date=target_date,
        notes=data.get("notes"),
        status=GoalStatus.ACTIVE,
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    """Get a specific savings goal with contributions."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)

    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    contributions = (
        db.session.query(GoalContribution)
        .filter_by(goal_id=goal_id)
        .order_by(GoalContribution.contributed_at.desc())
        .all()
    )

    result = _goal_to_dict(goal)
    result["contributions"] = [_contribution_to_dict(c) for c in contributions]
    return jsonify(result)


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    """Update a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)

    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = data["name"].strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        goal.name = name

    if "target_amount" in data:
        target_amount = _parse_amount(data["target_amount"])
        if target_amount is None or target_amount <= 0:
            return jsonify(error="invalid target_amount"), 400
        goal.target_amount = target_amount

    if "current_amount" in data:
        current_amount = _parse_amount(data["current_amount"])
        if current_amount is None or current_amount < 0:
            return jsonify(error="invalid current_amount"), 400
        goal.current_amount = current_amount
        # Auto-complete if target reached
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED

    if "target_date" in data:
        if data["target_date"]:
            try:
                goal.target_date = date.fromisoformat(data["target_date"])
            except ValueError:
                return jsonify(error="invalid target_date format"), 400
        else:
            goal.target_date = None

    if "status" in data:
        try:
            goal.status = GoalStatus(data["status"].upper())
        except ValueError:
            return jsonify(error="invalid status (ACTIVE, COMPLETED, CANCELLED)"), 400

    if "notes" in data:
        goal.notes = data["notes"]

    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    """Delete a savings goal and its contributions."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)

    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    # Delete associated contributions
    db.session.query(GoalContribution).filter_by(goal_id=goal_id).delete()
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")


# --- Contribution endpoints ---

@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    """Add a contribution to a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)

    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404

    data = request.get_json() or {}

    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="valid amount is required"), 400

    currency = data.get("currency") or goal.currency

    contribution = GoalContribution(
        user_id=uid,
        goal_id=goal_id,
        amount=amount,
        currency=currency,
        note=data.get("note"),
    )
    db.session.add(contribution)

    # Update goal's current amount
    goal.current_amount = (goal.current_amount or Decimal("0")) + amount

    # Auto-complete if target reached
    if goal.current_amount >= goal.target_amount:
        goal.status = GoalStatus.COMPLETED

    db.session.commit()
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    """List all contributions for a goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)

    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404

    contributions = (
        db.session.query(GoalContribution)
        .filter_by(goal_id=goal_id)
        .order_by(GoalContribution.contributed_at.desc())
        .all()
    )
    return jsonify([_contribution_to_dict(c) for c in contributions])


# --- Helper functions ---

def _goal_to_dict(goal: SavingsGoal) -> dict:
    progress = 0.0
    if goal.target_amount and goal.target_amount > 0:
        progress = float(goal.current_amount or 0) / float(goal.target_amount) * 100

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount or 0),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status.value if goal.status else GoalStatus.ACTIVE.value,
        "notes": goal.notes,
        "progress": round(progress, 2),
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
    }


def _contribution_to_dict(contribution: GoalContribution) -> dict:
    return {
        "id": contribution.id,
        "amount": float(contribution.amount),
        "currency": contribution.currency,
        "note": contribution.note,
        "contributed_at": contribution.contributed_at.isoformat() if contribution.contributed_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
