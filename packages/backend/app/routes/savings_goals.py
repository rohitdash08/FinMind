from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, Milestone, User
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")


@bp.get("")
@jwt_required()
def list_savings_goals():
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
def create_savings_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="valid target_amount required"), 400
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline"), 400
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        current_amount=_parse_amount(data.get("current_amount")) or Decimal("0"),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline,
        status=SavingsGoalStatus.ACTIVE,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, name)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal, include_milestones=True))


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
            return jsonify(error="valid target_amount required"), 400
        goal.target_amount = target_amount
    if "currency" in data:
        goal.currency = str(data.get("currency") or "INR")[:10]
    if "deadline" in data:
        if data.get("deadline"):
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            goal.deadline = None
    if "status" in data:
        raw_status = str(data.get("status") or "").upper()
        try:
            goal.status = SavingsGoalStatus(raw_status)
        except ValueError:
            return jsonify(error="invalid status"), 400
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="valid positive amount required"), 400
    goal.current_amount = Decimal(str(goal.current_amount)) + amount
    # Auto-mark completed if target reached
    if goal.current_amount >= goal.target_amount:
        goal.status = SavingsGoalStatus.COMPLETED
    # Check milestones
    for m in goal.milestones:
        if not m.reached and goal.current_amount >= m.target_amount:
            m.reached = True
            m.reached_at = datetime.utcnow()
    db.session.commit()
    logger.info(
        "Contribution to goal id=%s user=%s amount=%s",
        goal.id,
        uid,
        amount,
    )
    return jsonify(_goal_to_dict(goal, include_milestones=True))


# ---- Milestone endpoints ----


@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def create_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="valid target_amount required"), 400
    milestone = Milestone(
        goal_id=goal_id,
        name=name,
        target_amount=target_amount,
    )
    # Check if already reached
    if goal.current_amount >= target_amount:
        milestone.reached = True
        milestone.reached_at = datetime.utcnow()
    db.session.add(milestone)
    db.session.commit()
    logger.info("Created milestone id=%s goal_id=%s", milestone.id, goal_id)
    return jsonify(_milestone_to_dict(milestone)), 201


@bp.patch("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    milestone = db.session.get(Milestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        milestone.name = name
    if "target_amount" in data:
        target_amount = _parse_amount(data.get("target_amount"))
        if target_amount is None or target_amount <= 0:
            return jsonify(error="valid target_amount required"), 400
        milestone.target_amount = target_amount
    if "reached" in data:
        milestone.reached = bool(data.get("reached"))
        if milestone.reached and not milestone.reached_at:
            milestone.reached_at = datetime.utcnow()
        elif not milestone.reached:
            milestone.reached_at = None
    db.session.commit()
    logger.info("Updated milestone id=%s goal_id=%s", milestone_id, goal_id)
    return jsonify(_milestone_to_dict(milestone))


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    milestone = db.session.get(Milestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error="not found"), 404
    db.session.delete(milestone)
    db.session.commit()
    logger.info("Deleted milestone id=%s goal_id=%s", milestone_id, goal_id)
    return jsonify(message="deleted")


# ---- Helpers ----


def _goal_to_dict(g: SavingsGoal, include_milestones: bool = False) -> dict:
    d = {
        "id": g.id,
        "user_id": g.user_id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status.value if isinstance(g.status, SavingsGoalStatus) else g.status,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }
    if include_milestones:
        d["milestones"] = [
            _milestone_to_dict(m) for m in g.milestones.order_by(Milestone.target_amount)
        ]
    return d


def _milestone_to_dict(m: Milestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "name": m.name,
        "target_amount": float(m.target_amount),
        "reached": m.reached,
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
