from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, SavingsMilestone, SavingsContribution
from ..services import savings as savings_service

bp = Blueprint("savings", __name__)


@bp.post("")
@jwt_required()
def create_goal():
    """Create a new savings goal with auto-milestones."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    name = data.get("name")
    target_amount = data.get("target_amount")
    currency = data.get("currency", "INR")
    deadline = data.get("deadline")
    
    if not name:
        return jsonify(error="name is required"), 400
    if target_amount is None:
        return jsonify(error="target_amount is required"), 400
    
    deadline_date = None
    if deadline:
        try:
            deadline_date = date.fromisoformat(deadline)
        except ValueError:
            return jsonify(error="invalid deadline format, use ISO date"), 400
    
    try:
        goal = savings_service.create_goal(
            user_id=uid,
            name=name,
            target_amount=target_amount,
            currency=currency,
            deadline=deadline_date,
        )
    except ValueError as e:
        return jsonify(error=str(e)), 400
    
    return jsonify(
        id=goal.id,
        name=goal.name,
        target_amount=float(goal.target_amount),
        current_amount=float(goal.current_amount),
        currency=goal.currency,
        deadline=goal.deadline.isoformat() if goal.deadline else None,
        status=goal.status.value,
        created_at=goal.created_at.isoformat(),
    ), 201


@bp.get("")
@jwt_required()
def list_goals():
    """List all savings goals for the user."""
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    
    goals = savings_service.list_goals(uid, status_filter)
    
    return jsonify(
        [
            {
                "id": g.id,
                "name": g.name,
                "target_amount": float(g.target_amount),
                "current_amount": float(g.current_amount),
                "currency": g.currency,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "status": g.status.value,
                "created_at": g.created_at.isoformat(),
            }
            for g in goals
        ]
    )


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    """Get a specific savings goal with progress stats."""
    uid = int(get_jwt_identity())
    
    goal = savings_service.get_goal_with_progress(goal_id, uid)
    if not goal:
        return jsonify(error="Goal not found"), 404
    
    progress = savings_service.get_goal_progress(goal)
    
    return jsonify(
        {
            "id": goal.id,
            "name": goal.name,
            "target_amount": float(goal.target_amount),
            "current_amount": float(goal.current_amount),
            "currency": goal.currency,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "status": goal.status.value,
            "created_at": goal.created_at.isoformat(),
            "progress": progress,
        }
    )


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    """Update a savings goal."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    name = data.get("name")
    target_amount = data.get("target_amount")
    deadline = data.get("deadline")
    status = data.get("status")
    
    deadline_date = None
    if deadline:
        try:
            deadline_date = date.fromisoformat(deadline)
        except ValueError:
            return jsonify(error="invalid deadline format, use ISO date"), 400
    
    try:
        goal = savings_service.update_goal(
            goal_id=goal_id,
            user_id=uid,
            name=name,
            target_amount=target_amount,
            deadline=deadline_date,
            status=status,
        )
    except ValueError as e:
        return jsonify(error=str(e)), 400
    
    return jsonify(
        id=goal.id,
        name=goal.name,
        target_amount=float(goal.target_amount),
        current_amount=float(goal.current_amount),
        currency=goal.currency,
        deadline=goal.deadline.isoformat() if goal.deadline else None,
        status=goal.status.value,
        created_at=goal.created_at.isoformat(),
    )


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    """Delete a savings goal."""
    uid = int(get_jwt_identity())
    
    try:
        savings_service.delete_goal(goal_id, uid)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    
    return jsonify(deleted=True)


@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    """Add a contribution to a savings goal."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    amount = data.get("amount")
    notes = data.get("notes")
    
    if amount is None:
        return jsonify(error="amount is required"), 400
    
    try:
        contribution = savings_service.add_contribution(
            goal_id=goal_id,
            user_id=uid,
            amount=amount,
            notes=notes,
        )
    except ValueError as e:
        return jsonify(error=str(e)), 400
    
    return jsonify(
        id=contribution.id,
        goal_id=contribution.goal_id,
        amount=float(contribution.amount),
        contributed_at=contribution.contributed_at.isoformat(),
        notes=contribution.notes,
    ), 201


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    """List all contributions for a savings goal."""
    uid = int(get_jwt_identity())
    
    try:
        contributions = savings_service.list_contributions(goal_id, uid)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    
    return jsonify(
        [
            {
                "id": c.id,
                "goal_id": c.goal_id,
                "amount": float(c.amount),
                "contributed_at": c.contributed_at.isoformat(),
                "notes": c.notes,
            }
            for c in contributions
        ]
    )


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    """List all milestones for a savings goal."""
    uid = int(get_jwt_identity())
    
    try:
        milestones = savings_service.list_milestones(goal_id, uid)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    
    return jsonify(
        [
            {
                "id": m.id,
                "goal_id": m.goal_id,
                "name": m.name,
                "target_amount": float(m.target_amount),
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in milestones
        ]
    )


@bp.post("/<int:goal_id>/complete")
@jwt_required()
def complete_goal(goal_id: int):
    """Manually mark a savings goal as completed."""
    uid = int(get_jwt_identity())
    
    try:
        goal = savings_service.mark_goal_completed(goal_id, uid)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    
    return jsonify(
        id=goal.id,
        name=goal.name,
        status=goal.status.value,
    )


@bp.post("/<int:goal_id>/abandon")
@jwt_required()
def abandon_goal(goal_id: int):
    """Abandon a savings goal."""
    uid = int(get_jwt_identity())
    
    try:
        goal = savings_service.abandon_goal(goal_id, uid)
    except ValueError as e:
        return jsonify(error=str(e)), 404
    
    return jsonify(
        id=goal.id,
        name=goal.name,
        status=goal.status.value,
    )