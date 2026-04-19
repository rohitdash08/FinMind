from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, GoalStatus, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = db.session.query(SavingsGoal).filter_by(user_id=uid).order_by(SavingsGoal.created_at.desc()).all()
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    
    amount = _parse_amount(data.get("target_amount"))
    if amount is None:
        return jsonify(error="invalid target amount"), 400
        
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify(error="title required"), 400
        
    goal = SavingsGoal(
        user_id=uid,
        title=title,
        target_amount=amount,
        current_amount=_parse_amount(data.get("current_amount", 0)) or Decimal(0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=date.fromisoformat(data.get("deadline")) if data.get("deadline") else None,
        status=GoalStatus(data.get("status", "on-track"))
    )
    
    db.session.add(goal)
    db.session.commit()
    
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal))


@bp.patch("/goals/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
        
    data = request.get_json() or {}
    if "target_amount" in data:
        goal.target_amount = _parse_amount(data["target_amount"])
    if "current_amount" in data:
        goal.current_amount = _parse_amount(data["current_amount"])
    if "title" in data:
        goal.title = data["title"]
    if "status" in data:
        goal.status = GoalStatus(data["status"])
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
        
    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/goals/<int:goal_id>/milestones")
@jwt_required()
def add_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
        
    data = request.get_json() or {}
    amount = _parse_amount(data.get("target_amount"))
    if amount is None:
        return jsonify(error="invalid target amount"), 400
        
    milestone = SavingsMilestone(
        goal_id=goal.id,
        title=data.get("title", "New Milestone"),
        target_amount=amount
    )
    db.session.add(milestone)
    db.session.commit()
    return jsonify(_milestone_to_dict(milestone)), 201


def _goal_to_dict(g: SavingsGoal) -> dict:
    return {
        "id": g.id,
        "title": g.title,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status.value,
        "created_at": g.created_at.isoformat(),
        "milestones": [_milestone_to_dict(m) for g in [g] for m in g.milestones]
    }


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "target_amount": float(m.target_amount),
        "is_completed": m.is_completed,
        "completed_at": m.completed_at.isoformat() if m.completed_at else None
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
