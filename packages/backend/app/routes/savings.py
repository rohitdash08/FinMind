"""
Savings goals & milestones routes.

Milestones are computed from progress percentage:
  25% / 50% / 75% / 100% of target_amount reached
"""

from datetime import date, datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsDeposit, SavingsGoalStatus, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")

_MILESTONE_THRESHOLDS = [25, 50, 75, 100]


def _goal_to_dict(goal: SavingsGoal) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    pct = round((current / target) * 100, 2) if target > 0 else 0

    reached = [m for m in _MILESTONE_THRESHOLDS if pct >= m]
    next_milestone = next((m for m in _MILESTONE_THRESHOLDS if pct < m), None)

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "notes": goal.notes,
        "status": goal.status,
        "progress_pct": pct,
        "milestones_reached": reached,
        "next_milestone_pct": next_milestone,
        "created_at": goal.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Goals CRUD
# ---------------------------------------------------------------------------

@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter:
        q = q.filter_by(status=status_filter.upper())
    goals = q.order_by(SavingsGoal.created_at.desc()).all()
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
    try:
        target = float(data["target_amount"])
        if target <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="target_amount must be a positive number"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=target,
        current_amount=float(data.get("initial_amount", 0) or 0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
        notes=data.get("notes"),
        status=SavingsGoalStatus.ACTIVE.value,
    )
    db.session.add(goal)
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
        try:
            t = float(data["target_amount"])
            if t <= 0:
                raise ValueError
            goal.target_amount = t
        except (ValueError, TypeError):
            return jsonify(error="target_amount must be a positive number"), 400
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    if "notes" in data:
        goal.notes = data["notes"]
    if "status" in data:
        try:
            goal.status = SavingsGoalStatus(data["status"].upper()).value
        except ValueError:
            return jsonify(error=f"status must be one of {[s.value for s in SavingsGoalStatus]}"), 400

    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal_id, uid)
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


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------

@bp.post("/<int:goal_id>/deposits")
@jwt_required()
def add_deposit(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status == SavingsGoalStatus.COMPLETED.value:
        return jsonify(error="goal is already completed"), 400

    data = request.get_json() or {}
    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        return jsonify(error="amount must be a positive number"), 400

    dep = SavingsDeposit(
        goal_id=goal.id,
        user_id=uid,
        amount=amount,
        note=data.get("note"),
        deposited_at=date.fromisoformat(data["deposited_at"]) if data.get("deposited_at") else date.today(),
    )
    db.session.add(dep)

    goal.current_amount = float(goal.current_amount) + amount
    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = SavingsGoalStatus.COMPLETED.value

    db.session.commit()
    logger.info(
        "Deposit goal_id=%s user=%s amount=%s new_total=%s",
        goal_id, uid, amount, goal.current_amount,
    )
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>/deposits")
@jwt_required()
def list_deposits(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    deposits = (
        db.session.query(SavingsDeposit)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsDeposit.deposited_at.desc())
        .all()
    )
    return jsonify([
        {
            "id": d.id,
            "amount": float(d.amount),
            "note": d.note,
            "deposited_at": d.deposited_at.isoformat(),
            "created_at": d.created_at.isoformat(),
        }
        for d in deposits
    ])
