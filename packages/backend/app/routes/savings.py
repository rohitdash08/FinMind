"""Savings goals CRUD endpoints."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")

MILESTONE_PCTS = [25, 50, 75, 100]


def _goal_to_dict(g: SavingsGoal) -> dict:
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=g.id)
        .order_by(SavingsMilestone.percentage)
        .all()
    )
    progress = 0.0
    if g.target_amount and float(g.target_amount) > 0:
        progress = round(float(g.current_amount) / float(g.target_amount) * 100, 1)
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "active": g.active,
        "progress": min(progress, 100.0),
        "created_at": g.created_at.isoformat(),
        "milestones": [
            {
                "id": m.id,
                "label": m.label,
                "percentage": m.percentage,
                "target_amount": float(m.target_amount),
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in milestones
        ],
    }


def _create_milestones(goal: SavingsGoal) -> None:
    """Auto-generate milestones at 25%, 50%, 75%, 100%."""
    for pct in MILESTONE_PCTS:
        ms = SavingsMilestone(
            goal_id=goal.id,
            label=f"{pct}% of {goal.name}",
            percentage=pct,
            target_amount=Decimal(str(float(goal.target_amount) * pct / 100)),
            reached=False,
        )
        db.session.add(ms)


def _update_milestones(goal: SavingsGoal) -> None:
    """Mark milestones as reached based on current_amount."""
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id, reached=False)
        .all()
    )
    for ms in milestones:
        if goal.current_amount >= ms.target_amount:
            ms.reached = True
            ms.reached_at = datetime.utcnow()


def _parse_amount(raw) -> Decimal | None:
    try:
        val = Decimal(str(raw)).quantize(Decimal("0.01"))
        return val if val >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


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
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="valid target_amount required"), 400
    current = _parse_amount(data.get("current_amount", 0)) or Decimal("0")
    deadline = None
    if data.get("deadline"):
        try:
            from datetime import date
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline format"), 400
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target,
        current_amount=current,
        currency=data.get("currency", "INR"),
        deadline=deadline,
        active=True,
    )
    db.session.add(goal)
    db.session.flush()
    _create_milestones(goal)
    _update_milestones(goal)
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
    if "current_amount" in data:
        amt = _parse_amount(data["current_amount"])
        if amt is None:
            return jsonify(error="invalid current_amount"), 400
        goal.current_amount = amt
        _update_milestones(goal)
    if "target_amount" in data:
        amt = _parse_amount(data["target_amount"])
        if amt is None or amt <= 0:
            return jsonify(error="invalid target_amount"), 400
        goal.target_amount = amt
    if "deadline" in data:
        if data["deadline"]:
            try:
                from datetime import date
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            goal.deadline = None
    if "active" in data:
        goal.active = bool(data["active"])
    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.query(SavingsMilestone).filter_by(goal_id=goal.id).delete()
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")
