from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import GoalStatus, SavingsGoal, User
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status:
        q = q.filter(SavingsGoal.status == status.upper())
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
    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="invalid target_amount"), 400
    current = _parse_amount(data.get("current_amount") or 0) or Decimal("0")
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline"), 400
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target,
        current_amount=current,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s", goal.id, uid)
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
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        goal.name = name
    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="invalid target_amount"), 400
        goal.target_amount = target
    if "current_amount" in data:
        current = _parse_amount(data["current_amount"])
        if current is None or current < 0:
            return jsonify(error="invalid current_amount"), 400
        goal.current_amount = current
    if "currency" in data:
        goal.currency = str(data["currency"] or "INR")[:10]
    if "deadline" in data:
        if data["deadline"]:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            goal.deadline = None
    if "status" in data:
        status_val = str(data["status"] or "").upper()
        if status_val not in {s.value for s in GoalStatus}:
            return jsonify(error="invalid status"), 400
        goal.status = status_val
    # Auto-complete when current >= target
    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = GoalStatus.COMPLETED.value
    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status != GoalStatus.ACTIVE.value:
        return jsonify(error="goal is not active"), 400
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid amount"), 400
    goal.current_amount = Decimal(str(goal.current_amount)) + amount
    if goal.current_amount >= goal.target_amount:
        goal.status = GoalStatus.COMPLETED.value
    db.session.commit()
    logger.info("Deposit to goal id=%s amount=%s", goal.id, amount)
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
    return jsonify(message="deleted")


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress = round((current / target) * 100, 1) if target > 0 else 0
    milestones = []
    for pct in [25, 50, 75, 100]:
        milestones.append({
            "percentage": pct,
            "reached": progress >= pct,
        })
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "progress": progress,
        "milestones": milestones,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
