from datetime import date, datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, GoalStatus, User
import logging
import math

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")

MILESTONE_PCTS = [25, 50, 75, 100]


def _goal_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    pct = round((current / target * 100), 1) if target > 0 else 0.0

    # Compute milestones reached
    milestones = [
        {"pct": m, "amount": round(target * m / 100, 2), "reached": current >= target * m / 100}
        for m in MILESTONE_PCTS
    ]

    # Days remaining
    days_remaining = None
    if g.deadline:
        delta = (g.deadline - date.today()).days
        days_remaining = max(delta, 0)

    # Monthly target auto-calc if not set
    monthly_target = float(g.monthly_target) if g.monthly_target else None
    if monthly_target is None and days_remaining and days_remaining > 0:
        months_left = max(days_remaining / 30.44, 1)
        monthly_target = round((target - current) / months_left, 2)

    return {
        "id": g.id,
        "title": g.title,
        "description": g.description,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "monthly_target": monthly_target,
        "icon": g.icon,
        "progress_pct": pct,
        "milestones": milestones,
        "days_remaining": days_remaining,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat() if g.updated_at else g.created_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter:
        q = q.filter_by(status=status_filter.upper())
    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    if not data.get("title") or not data.get("target_amount"):
        return jsonify(error="title and target_amount are required"), 400

    g = SavingsGoal(
        user_id=uid,
        title=data["title"],
        description=data.get("description"),
        target_amount=float(data["target_amount"]),
        current_amount=float(data.get("current_amount", 0)),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
        monthly_target=float(data["monthly_target"]) if data.get("monthly_target") else None,
        icon=data.get("icon"),
        status=GoalStatus.ACTIVE.value,
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created goal id=%s user=%s title=%s", g.id, uid, g.title)
    return jsonify(_goal_dict(g)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_dict(g))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "title" in data:
        g.title = data["title"]
    if "description" in data:
        g.description = data["description"]
    if "target_amount" in data:
        g.target_amount = float(data["target_amount"])
    if "current_amount" in data:
        g.current_amount = float(data["current_amount"])
    if "currency" in data:
        g.currency = data["currency"]
    if "deadline" in data:
        g.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    if "monthly_target" in data:
        g.monthly_target = float(data["monthly_target"]) if data["monthly_target"] else None
    if "icon" in data:
        g.icon = data["icon"]
    if "status" in data:
        g.status = data["status"].upper()

    # Auto-complete when target reached
    if float(g.current_amount) >= float(g.target_amount):
        g.status = GoalStatus.COMPLETED.value

    g.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated goal id=%s user=%s", g.id, uid)
    return jsonify(_goal_dict(g))


@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id: int):
    """Add funds to a savings goal."""
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400

    g.current_amount = float(g.current_amount) + amount
    if float(g.current_amount) >= float(g.target_amount):
        g.status = GoalStatus.COMPLETED.value
    g.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Deposited %.2f into goal id=%s user=%s", amount, g.id, uid)
    return jsonify(_goal_dict(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(g)
    db.session.commit()
    logger.info("Deleted goal id=%s user=%s", g.id, uid)
    return jsonify(message="deleted")
