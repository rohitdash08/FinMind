from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, SavingsGoalStatus, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": g.id,
                "name": g.name,
                "target_amount": float(g.target_amount),
                "current_amount": float(g.current_amount),
                "currency": g.currency,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "status": g.status,
                "created_at": g.created_at.isoformat(),
            }
            for g in goals
        ]
    )


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    deadline = None
    if data.get("deadline"):
        deadline = date.fromisoformat(data["deadline"])

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=data["target_amount"],
        current_amount=data.get("current_amount", 0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline,
        status=SavingsGoalStatus.ACTIVE.value,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, goal.name)
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(id=goal.id), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal_id, user_id=uid)
        .order_by(SavingsMilestone.target_amount)
        .all()
    )

    return jsonify(
        {
            "id": goal.id,
            "name": goal.name,
            "target_amount": float(goal.target_amount),
            "current_amount": float(goal.current_amount),
            "currency": goal.currency,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "status": goal.status,
            "created_at": goal.created_at.isoformat(),
            "milestones": [
                {
                    "id": m.id,
                    "title": m.title,
                    "target_amount": float(m.target_amount),
                    "reached": m.reached,
                    "reached_at": m.reached_at.isoformat() if m.reached_at else None,
                }
                for m in milestones
            ],
        }
    )


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
        goal.target_amount = data["target_amount"]
    if "current_amount" in data:
        goal.current_amount = data["current_amount"]
        if goal.current_amount >= goal.target_amount:
            goal.status = SavingsGoalStatus.COMPLETED.value
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    if "status" in data:
        goal.status = data["status"]

    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(message="updated")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    """Add money to a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400

    goal.current_amount = float(goal.current_amount) + amount

    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal_id, user_id=uid, reached=False)
        .all()
    )
    for m in milestones:
        if goal.current_amount >= float(m.target_amount):
            m.reached = True
            m.reached_at = date.today()

    if goal.current_amount >= goal.target_amount:
        goal.status = SavingsGoalStatus.COMPLETED.value

    db.session.commit()
    logger.info(
        "Contributed %.2f to goal id=%s user=%s new_current=%.2f",
        amount, goal.id, uid, float(goal.current_amount),
    )
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(
        {
            "message": "contribution recorded",
            "current_amount": float(goal.current_amount),
            "status": goal.status,
        }
    )


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.query(SavingsMilestone).filter_by(goal_id=goal_id).delete()
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(message="deleted")


# ── Milestones ──────────────────────────────────────────────────────────────


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal_id, user_id=uid)
        .order_by(SavingsMilestone.target_amount)
        .all()
    )
    return jsonify(
        [
            {
                "id": m.id,
                "title": m.title,
                "target_amount": float(m.target_amount),
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in milestones
        ]
    )


@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def add_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    target = float(data["target_amount"])

    reached = float(goal.current_amount) >= target
    reached_at = date.today() if reached else None

    milestone = SavingsMilestone(
        goal_id=goal_id,
        user_id=uid,
        title=data["title"],
        target_amount=target,
        reached=reached,
        reached_at=reached_at,
    )
    db.session.add(milestone)
    db.session.commit()
    logger.info(
        "Added milestone id=%s to goal id=%s user=%s target=%.2f reached=%s",
        milestone.id, goal_id, uid, target, reached,
    )
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(id=milestone.id), 201


@bp.patch("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "title" in data:
        milestone.title = data["title"]
    if "target_amount" in data:
        milestone.target_amount = data["target_amount"]
        goal = db.session.get(SavingsGoal, goal_id)
        if goal:
            milestone.reached = float(goal.current_amount) >= float(milestone.target_amount)
            milestone.reached_at = date.today() if milestone.reached else None

    db.session.commit()
    logger.info("Updated milestone id=%s user=%s", milestone_id, uid)
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(message="updated")


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(milestone)
    db.session.commit()
    logger.info("Deleted milestone id=%s user=%s", milestone_id, uid)
    cache_delete_patterns([f"user:{uid}:savings_goals*"])
    return jsonify(message="deleted")
