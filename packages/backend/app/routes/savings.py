from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    SavingsGoal,
    SavingsGoalStatus,
    SavingsMilestone,
    SavingsContribution,
    User,
)
from ..services import savings as savings_service
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter:
        try:
            q = q.filter(SavingsGoal.status == SavingsGoalStatus(status_filter))
        except ValueError:
            pass  # ignore invalid status
    items = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_to_dict(g) for g in items])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    target = savings_service.parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="invalid target_amount"), 400
    currency = data.get("currency") or (user.preferred_currency if user else "INR")
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data.get("deadline"))
        except ValueError:
            return jsonify(error="invalid deadline"), 400
    goal = savings_service.create_goal(
        user_id=uid,
        name=name,
        target_amount=target,
        currency=currency,
        deadline=deadline,
    )
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal, include_progress=True))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = data.get("name", "").strip()
        if not name:
            return jsonify(error="name required"), 400
        goal.name = name
    if "target_amount" in data:
        target = savings_service.parse_amount(data.get("target_amount"))
        if target is None or target <= 0:
            return jsonify(error="invalid target_amount"), 400
        goal.target_amount = target
    if "deadline" in data:
        if data.get("deadline"):
            try:
                goal.deadline = date.fromisoformat(data.get("deadline"))
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            goal.deadline = None
    if "status" in data:
        try:
            goal.status = SavingsGoalStatus(data.get("status"))
        except ValueError:
            return jsonify(error="invalid status"), 400
    db.session.commit()
    return jsonify(_goal_to_dict(goal, include_progress=True))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    # Delete related milestones and contributions first
    db.session.query(SavingsMilestone).filter_by(goal_id=goal.id).delete()
    db.session.query(SavingsContribution).filter_by(goal_id=goal.id).delete()
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status == SavingsGoalStatus.COMPLETED:
        return jsonify(error="goal already completed"), 400
    data = request.get_json() or {}
    amount = savings_service.parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid amount"), 400
    notes = (data.get("notes") or "").strip()
    if notes and len(notes) > 500:
        notes = notes[:500]
    contrib = savings_service.add_contribution(goal, amount, notes or None)
    logger.info("Added contribution goal=%s amount=%s user=%s", goal_id, amount, uid)
    return jsonify(_contribution_to_dict(contrib, goal)), 201


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id)
        .order_by(SavingsMilestone.target_amount)
        .all()
    )
    return jsonify([_milestone_to_dict(m) for m in items])


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=goal.id)
        .order_by(SavingsContribution.contributed_at.desc())
        .all()
    )
    return jsonify([_contribution_to_dict(c, goal) for c in items])


@bp.post("/<int:goal_id>/complete")
@jwt_required()
def complete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    savings_service.mark_goal_completed(goal)
    return jsonify(_goal_to_dict(goal))


@bp.post("/<int:goal_id>/abandon")
@jwt_required()
def abandon_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    savings_service.abandon_goal(goal)
    return jsonify(_goal_to_dict(goal))


def _goal_to_dict(g: SavingsGoal, include_progress: bool = False) -> dict:
    result = {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status.value,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }
    if include_progress:
        result["progress"] = savings_service.get_goal_progress(g)
    return result


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "name": m.name,
        "target_amount": float(m.target_amount),
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
    }


def _contribution_to_dict(
    c: SavingsContribution, goal: SavingsGoal | None = None
) -> dict:
    result = {
        "id": c.id,
        "goal_id": c.goal_id,
        "amount": float(c.amount),
        "contributed_at": c.contributed_at.isoformat() if c.contributed_at else None,
        "notes": c.notes or "",
    }
    if goal:
        result["goal_name"] = goal.name
    return result
