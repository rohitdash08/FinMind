"""
Routes for savings goal tracking and milestones.

Endpoints:
  GET    /savings                         - list all savings goals for the user
  POST   /savings                         - create a new savings goal
  GET    /savings/<id>                    - get a single savings goal with milestones
  PATCH  /savings/<id>                    - update goal fields
  DELETE /savings/<id>                    - cancel (soft-delete) a goal
  POST   /savings/<id>/deposit            - add funds toward a goal
  GET    /savings/<id>/milestones         - list milestones for a goal
  POST   /savings/<id>/milestones         - create a milestone for a goal
  PATCH  /savings/<id>/milestones/<mid>   - update a milestone
  DELETE /savings/<id>/milestones/<mid>   - delete a milestone
"""

from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, SavingsMilestone, User

import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_amount(value) -> Decimal | None:
    """Return a positive Decimal or None on failure."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        if d <= 0:
            return None
        return d
    except InvalidOperation:
        return None


def _goal_to_dict(goal: SavingsGoal, milestones: list | None = None) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    progress_pct = round((current / target * 100), 2) if target > 0 else 0.0
    data = {
        "id": goal.id,
        "user_id": goal.user_id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status.value if hasattr(goal.status, "value") else goal.status,
        "notes": goal.notes,
        "progress_pct": progress_pct,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }
    if milestones is not None:
        data["milestones"] = [_milestone_to_dict(m) for m in milestones]
    return data


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "user_id": m.user_id,
        "name": m.name,
        "target_amount": float(m.target_amount),
        "reached": m.reached,
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
        "created_at": m.created_at.isoformat(),
    }


def _check_and_mark_milestones(goal: SavingsGoal) -> list[SavingsMilestone]:
    """Mark any un-reached milestones that the current amount has met."""
    newly_reached = []
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id, reached=False)
        .all()
    )
    for m in milestones:
        if goal.current_amount >= m.target_amount:
            m.reached = True
            m.reached_at = datetime.utcnow()
            newly_reached.append(m)
    return newly_reached


def _maybe_complete_goal(goal: SavingsGoal) -> bool:
    """Mark goal as COMPLETED if current_amount >= target_amount."""
    if (
        goal.status == SavingsGoalStatus.ACTIVE
        and goal.current_amount >= goal.target_amount
    ):
        goal.status = SavingsGoalStatus.COMPLETED
        return True
    return False


# ---------------------------------------------------------------------------
# Goal CRUD
# ---------------------------------------------------------------------------

@bp.get("")
@jwt_required()
def list_goals():
    """Return all savings goals for the authenticated user."""
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter:
        try:
            q = q.filter(SavingsGoal.status == SavingsGoalStatus(status_filter.upper()))
        except ValueError:
            return jsonify(error="invalid status filter"), 400
    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
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
    if target_amount is None:
        return jsonify(error="target_amount must be a positive number"), 400

    initial_amount = _parse_amount(data.get("current_amount") or data.get("initial_amount") or 0)
    if initial_amount is None:
        initial_amount = Decimal("0")

    currency = (data.get("currency") or (user.preferred_currency if user else "INR"))

    target_date = None
    if data.get("target_date"):
        try:
            target_date = date.fromisoformat(data["target_date"])
        except ValueError:
            return jsonify(error="invalid target_date, use YYYY-MM-DD"), 400
        if target_date < date.today():
            return jsonify(error="target_date must be today or in the future"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        current_amount=initial_amount,
        currency=currency,
        target_date=target_date,
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(goal)
    db.session.flush()  # get goal.id before milestone checks

    _maybe_complete_goal(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, goal.name)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    """Return a single savings goal with its milestones."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id)
        .order_by(SavingsMilestone.target_amount.asc())
        .all()
    )
    return jsonify(_goal_to_dict(goal, milestones=milestones))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    """Update name, notes, target_amount, target_date, or status of a goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status == SavingsGoalStatus.CANCELLED:
        return jsonify(error="cannot update a cancelled goal"), 400

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        goal.name = name

    if "notes" in data:
        goal.notes = (data["notes"] or "").strip() or None

    if "target_amount" in data:
        target_amount = _parse_amount(data["target_amount"])
        if target_amount is None:
            return jsonify(error="target_amount must be a positive number"), 400
        goal.target_amount = target_amount

    if "target_date" in data:
        if data["target_date"] is None:
            goal.target_date = None
        else:
            try:
                goal.target_date = date.fromisoformat(data["target_date"])
            except ValueError:
                return jsonify(error="invalid target_date, use YYYY-MM-DD"), 400

    if "status" in data:
        try:
            new_status = SavingsGoalStatus(str(data["status"]).upper())
        except ValueError:
            return jsonify(error="invalid status"), 400
        goal.status = new_status

    goal.updated_at = datetime.utcnow()
    _maybe_complete_goal(goal)
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    """Cancel (soft-delete) a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    goal.status = SavingsGoalStatus.CANCELLED
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Cancelled savings goal id=%s user=%s", goal.id, uid)
    return jsonify(message="goal cancelled"), 200


# ---------------------------------------------------------------------------
# Deposit endpoint
# ---------------------------------------------------------------------------

@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id: int):
    """
    Add funds toward a savings goal.

    Body:
      amount (required) - positive number to add
    """
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status == SavingsGoalStatus.CANCELLED:
        return jsonify(error="cannot deposit into a cancelled goal"), 400

    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="amount must be a positive number"), 400

    goal.current_amount = Decimal(str(goal.current_amount)) + amount
    goal.updated_at = datetime.utcnow()

    newly_reached = _check_and_mark_milestones(goal)
    completed = _maybe_complete_goal(goal)

    db.session.commit()
    logger.info(
        "Deposit goal id=%s user=%s amount=%s new_total=%s completed=%s milestones_reached=%s",
        goal.id, uid, amount, goal.current_amount, completed, len(newly_reached),
    )
    return jsonify(
        goal=_goal_to_dict(goal),
        newly_reached_milestones=[_milestone_to_dict(m) for m in newly_reached],
        goal_completed=completed,
    ), 200


# ---------------------------------------------------------------------------
# Milestone CRUD
# ---------------------------------------------------------------------------

@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    """List milestones for a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsMilestone.target_amount.asc())
        .all()
    )
    return jsonify([_milestone_to_dict(m) for m in milestones])


@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def create_milestone(goal_id: int):
    """Create a milestone checkpoint for a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status == SavingsGoalStatus.CANCELLED:
        return jsonify(error="cannot add milestones to a cancelled goal"), 400

    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None:
        return jsonify(error="target_amount must be a positive number"), 400

    if target_amount > goal.target_amount:
        return jsonify(
            error="milestone target_amount cannot exceed goal target_amount"
        ), 400

    milestone = SavingsMilestone(
        goal_id=goal.id,
        user_id=uid,
        name=name,
        target_amount=target_amount,
    )
    # Auto-mark as reached if current savings already meet it
    if goal.current_amount >= target_amount:
        milestone.reached = True
        milestone.reached_at = datetime.utcnow()

    db.session.add(milestone)
    db.session.commit()
    logger.info(
        "Created milestone id=%s goal_id=%s user=%s", milestone.id, goal.id, uid
    )
    return jsonify(_milestone_to_dict(milestone)), 201


@bp.patch("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(goal_id: int, milestone_id: int):
    """Update a milestone's name or target_amount."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id or milestone.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        milestone.name = name

    if "target_amount" in data:
        target_amount = _parse_amount(data["target_amount"])
        if target_amount is None:
            return jsonify(error="target_amount must be a positive number"), 400
        if target_amount > goal.target_amount:
            return jsonify(
                error="milestone target_amount cannot exceed goal target_amount"
            ), 400
        milestone.target_amount = target_amount
        # Re-evaluate reached status
        if not milestone.reached and goal.current_amount >= target_amount:
            milestone.reached = True
            milestone.reached_at = datetime.utcnow()

    db.session.commit()
    return jsonify(_milestone_to_dict(milestone))


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    """Delete a milestone."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id or milestone.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(milestone)
    db.session.commit()
    logger.info(
        "Deleted milestone id=%s goal_id=%s user=%s", milestone_id, goal_id, uid
    )
    return jsonify(message="milestone deleted"), 200