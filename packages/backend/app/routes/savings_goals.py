from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, User
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")

MILESTONE_PERCENTS = [25, 50, 75, 100]


def _goal_to_dict(g: SavingsGoal) -> dict:
    progress = (
        float(g.current_amount / g.target_amount * 100)
        if g.target_amount > 0
        else 0.0
    )
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "progress": round(min(progress, 100.0), 2),
        "active": g.active,
        "created_at": g.created_at.isoformat(),
        "milestones": [
            {
                "id": m.id,
                "percent": m.percent,
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in sorted(g.milestones, key=lambda x: x.percent)
        ],
    }


def _create_milestones(goal: SavingsGoal):
    for pct in MILESTONE_PERCENTS:
        ms = SavingsMilestone(goal_id=goal.id, percent=pct)
        db.session.add(ms)


def _update_milestones(goal: SavingsGoal):
    if goal.target_amount <= 0:
        return
    progress = float(goal.current_amount / goal.target_amount * 100)
    for ms in goal.milestones:
        if not ms.reached and progress >= ms.percent:
            ms.reached = True
            ms.reached_at = datetime.utcnow()


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid, active=True)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    if not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount are required"), 400

    target = Decimal(str(data["target_amount"]))
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=target,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=(date.fromisoformat(data["deadline"]) if data.get("deadline") else None),
    )
    db.session.add(goal)
    db.session.flush()
    _create_milestones(goal)
    db.session.commit()

    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, goal.name)
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

    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        goal.target_amount = Decimal(str(data["target_amount"]))
    if "currency" in data:
        goal.currency = data["currency"]
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None

    _update_milestones(goal)
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    goal.active = False
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal.id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = Decimal(str(data.get("amount", 0)))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400

    goal.current_amount = goal.current_amount + amount
    _update_milestones(goal)
    db.session.commit()

    logger.info(
        "Contribution to goal id=%s user=%s amount=%s new_total=%s",
        goal.id, uid, amount, goal.current_amount,
    )
    return jsonify(_goal_to_dict(goal))
