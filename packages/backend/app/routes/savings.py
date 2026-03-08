from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("")
@jwt_required()
def list_savings_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_savings_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="invalid target_amount"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data.get("deadline"))
        except ValueError:
            return jsonify(error="invalid deadline"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        current_amount=Decimal("0"),
        currency=(data.get("currency") or (user.preferred_currency if user else "INR")),
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()

    # Handle milestones if provided
    milestones = data.get("milestones", [])
    for m in milestones:
        milestone_title = (m.get("title") or "").strip()
        milestone_amount = _parse_amount(m.get("target_amount"))
        if milestone_title and milestone_amount:
            ms = SavingsMilestone(
                goal_id=goal.id,
                title=milestone_title,
                target_amount=milestone_amount,
            )
            db.session.add(ms)
    db.session.commit()

    logger.info("Created savings goal id=%s user=%s target=%s", goal.id, uid, target_amount)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        goal.name = name

    if "target_amount" in data:
        target_amount = _parse_amount(data.get("target_amount"))
        if target_amount is None or target_amount <= 0:
            return jsonify(error="invalid target_amount"), 400
        goal.target_amount = target_amount

    if "current_amount" in data:
        current_amount = _parse_amount(data.get("current_amount"))
        if current_amount is None:
            return jsonify(error="invalid current_amount"), 400
        goal.current_amount = current_amount
        # Check if goal is completed
        if current_amount >= goal.target_amount and not goal.completed:
            goal.completed = True
            _check_milestones(goal)

    if "deadline" in data:
        if data.get("deadline"):
            try:
                goal.deadline = date.fromisoformat(data.get("deadline"))
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            goal.deadline = None

    if "currency" in data:
        goal.currency = str(data.get("currency") or "INR")[:10]

    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    # Delete associated milestones first
    db.session.query(SavingsMilestone).filter_by(goal_id=goal_id).delete()
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute_to_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid amount"), 400

    goal.current_amount = goal.current_amount + amount

    # Check if goal is now completed
    if goal.current_amount >= goal.target_amount and not goal.completed:
        goal.completed = True

    _check_milestones(goal)
    db.session.commit()

    return jsonify(_goal_to_dict(goal))


# Milestone endpoints
@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
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
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title required"), 400

    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="invalid target_amount"), 400

    milestone = SavingsMilestone(
        goal_id=goal_id,
        title=title,
        target_amount=target_amount,
    )
    db.session.add(milestone)
    db.session.commit()

    # Check if this milestone is already reached
    _check_milestones(goal)

    return jsonify(_milestone_to_dict(milestone)), 201


@bp.patch("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify(error="title required"), 400
        milestone.title = title

    if "target_amount" in data:
        target_amount = _parse_amount(data.get("target_amount"))
        if target_amount is None or target_amount <= 0:
            return jsonify(error="invalid target_amount"), 400
        milestone.target_amount = target_amount

    db.session.commit()
    return jsonify(_milestone_to_dict(milestone))


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error="not found"), 404

    db.session.delete(milestone)
    db.session.commit()
    return jsonify(message="deleted")


def _goal_to_dict(g: SavingsGoal) -> dict:
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=g.id)
        .order_by(SavingsMilestone.target_amount.asc())
        .all()
    )
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "completed": g.completed,
        "progress_percent": round(float(g.current_amount) / float(g.target_amount) * 100, 1)
        if g.target_amount > 0
        else 0,
        "milestones": [_milestone_to_dict(m) for m in milestones],
        "created_at": g.created_at.isoformat(),
    }


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "title": m.title,
        "target_amount": float(m.target_amount),
        "reached": m.reached,
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _check_milestones(goal: SavingsGoal):
    """Check and update milestone completion status"""
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id, reached=False)
        .order_by(SavingsMilestone.target_amount.asc())
        .all()
    )
    from datetime import datetime

    for m in milestones:
        if goal.current_amount >= m.target_amount:
            m.reached = True
            m.reached_at = datetime.utcnow()
