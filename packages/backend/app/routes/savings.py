from datetime import date, datetime
from math import ceil

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _compute_status(goal: SavingsGoal) -> str:
    current = float(goal.current_amount)
    target = float(goal.target_amount)

    if current >= target:
        return "completed"

    if not goal.deadline:
        return "on-track"

    today = date.today()
    if goal.deadline <= today:
        return "behind"

    created = goal.created_at.date() if goal.created_at else today
    total_days = (goal.deadline - created).days
    elapsed_days = (today - created).days

    if total_days <= 0:
        return "on-track"

    expected = target * (elapsed_days / total_days)
    if current >= expected * 1.05:
        return "ahead"
    if current < expected * 0.95:
        return "behind"
    return "on-track"


def _monthly_target(goal: SavingsGoal) -> float:
    if not goal.deadline:
        return 0.0
    remaining = float(goal.target_amount) - float(goal.current_amount)
    if remaining <= 0:
        return 0.0
    today = date.today()
    months_remaining = (
        (goal.deadline.year - today.year) * 12
        + (goal.deadline.month - today.month)
    )
    if months_remaining <= 0:
        return remaining
    return round(remaining / months_remaining, 2)


def _goal_to_dict(goal: SavingsGoal) -> dict:
    return {
        "id": goal.id,
        "title": goal.title,
        "target": float(goal.target_amount),
        "current": float(goal.current_amount),
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "monthlyTarget": _monthly_target(goal),
        "status": _compute_status(goal),
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_to_dict(g) for g in items])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400

    try:
        target_amount = float(data["target_amount"])
        if target_amount <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return jsonify(error="target_amount must be a positive number"), 400

    current_amount = 0.0
    if "current_amount" in data:
        try:
            current_amount = max(0.0, float(data["current_amount"]))
        except (ValueError, TypeError):
            return jsonify(error="current_amount must be a number"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="deadline must be YYYY-MM-DD"), 400

    currency = data.get("currency") or (
        user.preferred_currency if user else "INR"
    )

    goal = SavingsGoal(
        user_id=uid,
        title=title,
        target_amount=target_amount,
        current_amount=current_amount,
        currency=currency,
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s title=%s", goal.id, uid, title)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify(error="title cannot be empty"), 400
        goal.title = title

    if "target_amount" in data:
        try:
            val = float(data["target_amount"])
            if val <= 0:
                raise ValueError
            goal.target_amount = val
        except (ValueError, TypeError):
            return jsonify(error="target_amount must be a positive number"), 400

    if "current_amount" in data:
        try:
            goal.current_amount = max(0.0, float(data["current_amount"]))
        except (ValueError, TypeError):
            return jsonify(error="current_amount must be a number"), 400

    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="deadline must be YYYY-MM-DD"), 400

    if "currency" in data:
        goal.currency = data["currency"] or "INR"

    goal.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal_id, uid)
    return jsonify(_goal_to_dict(goal))


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return jsonify(error="amount must be a positive number"), 400

    goal.current_amount = float(goal.current_amount) + amount
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info(
        "Contributed %.2f to goal id=%s user=%s new_total=%.2f",
        amount, goal_id, uid, float(goal.current_amount),
    )
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")
