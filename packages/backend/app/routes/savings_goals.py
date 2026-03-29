from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import ceil

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalMilestone, User
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")


def _goal_status(goal: SavingsGoal) -> str:
    if float(goal.current_amount) >= float(goal.target_amount):
        return "COMPLETED"
    if not goal.deadline:
        return "ON_TRACK"
    today = date.today()
    if goal.deadline <= today:
        return "BEHIND"
    total_days = (goal.deadline - goal.created_at.date()).days or 1
    elapsed_days = (today - goal.created_at.date()).days
    expected_progress = elapsed_days / total_days
    actual_progress = float(goal.current_amount) / float(goal.target_amount)
    if actual_progress >= expected_progress + 0.05:
        return "AHEAD"
    if actual_progress < expected_progress - 0.05:
        return "BEHIND"
    return "ON_TRACK"


def _monthly_target(goal: SavingsGoal) -> float | None:
    if not goal.deadline:
        return None
    today = date.today()
    remaining = float(goal.target_amount) - float(goal.current_amount)
    if remaining <= 0:
        return 0.0
    months_left = (
        (goal.deadline.year - today.year) * 12
        + (goal.deadline.month - today.month)
    )
    if months_left <= 0:
        return round(remaining, 2)
    return round(remaining / months_left, 2)


def _goal_to_dict(g: SavingsGoal) -> dict:
    return {
        "id": g.id,
        "title": g.title,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": _goal_status(g),
        "monthly_target": _monthly_target(g),
        "created_at": g.created_at.isoformat(),
    }


def _milestone_to_dict(m: SavingsGoalMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "title": m.title,
        "amount": float(m.amount),
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
        "created_at": m.created_at.isoformat(),
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _check_milestones(goal: SavingsGoal):
    """Mark milestones as reached when current_amount meets their threshold."""
    milestones = (
        db.session.query(SavingsGoalMilestone)
        .filter_by(goal_id=goal.id)
        .filter(SavingsGoalMilestone.reached_at.is_(None))
        .all()
    )
    now = datetime.utcnow()
    for m in milestones:
        if float(goal.current_amount) >= float(m.amount):
            m.reached_at = now


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
        return jsonify(error="title required"), 400
    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="invalid target_amount"), 400
    current = _parse_amount(data.get("current_amount", 0)) or Decimal("0.00")
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline"), 400
    g = SavingsGoal(
        user_id=uid,
        title=title,
        target_amount=target,
        current_amount=current,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline,
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s title=%s", g.id, uid, g.title)
    return jsonify(_goal_to_dict(g)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(g))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify(error="title required"), 400
        g.title = title
    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="invalid target_amount"), 400
        g.target_amount = target
    if "current_amount" in data:
        current = _parse_amount(data["current_amount"])
        if current is None or current < 0:
            return jsonify(error="invalid current_amount"), 400
        g.current_amount = current
    if "currency" in data:
        g.currency = str(data["currency"] or "INR")[:10]
    if "deadline" in data:
        if data["deadline"]:
            try:
                g.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            g.deadline = None
    _check_milestones(g)
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", g.id, uid)
    return jsonify(_goal_to_dict(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(g)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", g.id, uid)
    return jsonify(message="deleted")


# --- Milestones ---


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        db.session.query(SavingsGoalMilestone)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsGoalMilestone.amount)
        .all()
    )
    return jsonify([_milestone_to_dict(m) for m in items])


@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def create_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title required"), 400
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid amount"), 400
    m = SavingsGoalMilestone(
        goal_id=goal_id,
        title=title,
        amount=amount,
    )
    if float(g.current_amount) >= float(amount):
        m.reached_at = datetime.utcnow()
    db.session.add(m)
    db.session.commit()
    logger.info("Created milestone id=%s goal=%s", m.id, goal_id)
    return jsonify(_milestone_to_dict(m)), 201


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    m = db.session.get(SavingsGoalMilestone, milestone_id)
    if not m or m.goal_id != goal_id:
        return jsonify(error="not found"), 404
    db.session.delete(m)
    db.session.commit()
    logger.info("Deleted milestone id=%s goal=%s", milestone_id, goal_id)
    return jsonify(message="deleted")
