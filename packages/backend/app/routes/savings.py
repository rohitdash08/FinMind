from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _serialize_goal(goal):
    pct = 0
    if goal.target_amount and float(goal.target_amount) > 0:
        pct = round(min(100, float(goal.current_amount or 0) / float(goal.target_amount) * 100), 1)
    milestones = []
    for m in [25, 50, 75, 100]:
        if pct >= m:
            milestones.append({"percent": m, "reached": True})
        else:
            milestones.append({"percent": m, "reached": False})
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": str(goal.target_amount),
        "current_amount": str(goal.current_amount),
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "icon": goal.icon,
        "is_completed": goal.is_completed,
        "progress_percent": pct,
        "milestones": milestones,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = db.session.query(SavingsGoal).filter_by(user_id=uid).order_by(SavingsGoal.created_at.desc()).all()
    return jsonify(goals=[_serialize_goal(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount required"), 400
    try:
        target = Decimal(str(data["target_amount"]))
        if target <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return jsonify(error="target_amount must be a positive number"), 400

    current = Decimal(str(data.get("current_amount", 0)))
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline format, use YYYY-MM-DD"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"][:200],
        target_amount=target,
        current_amount=current,
        currency=data.get("currency", "INR"),
        deadline=deadline,
        icon=data.get("icon"),
        is_completed=current >= target,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("User %s created savings goal %s (target=%s)", uid, goal.name, goal.target_amount)
    return jsonify(_serialize_goal(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    contributions = db.session.query(SavingsContribution).filter_by(goal_id=goal_id).order_by(SavingsContribution.created_at.desc()).all()
    return jsonify(
        goal=_serialize_goal(goal),
        contributions=[{
            "id": c.id,
            "amount": str(c.amount),
            "notes": c.notes,
            "created_at": c.created_at.isoformat(),
        } for c in contributions],
    )


@bp.put("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    data = request.get_json()
    if not data:
        return jsonify(error="no data provided"), 400
    if "name" in data:
        goal.name = data["name"][:200]
    if "target_amount" in data:
        try:
            goal.target_amount = Decimal(str(data["target_amount"]))
        except (InvalidOperation, ValueError):
            return jsonify(error="invalid target_amount"), 400
    if "current_amount" in data:
        try:
            goal.current_amount = Decimal(str(data["current_amount"]))
        except (InvalidOperation, ValueError):
            return jsonify(error="invalid current_amount"), 400
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    if "icon" in data:
        goal.icon = data["icon"]
    if "currency" in data:
        goal.currency = data["currency"]
    goal.is_completed = goal.current_amount >= goal.target_amount
    db.session.commit()
    return jsonify(_serialize_goal(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    db.session.query(SavingsContribution).filter_by(goal_id=goal_id).delete()
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="goal deleted"), 200


@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    data = request.get_json()
    if not data or not data.get("amount"):
        return jsonify(error="amount required"), 400
    try:
        amount = Decimal(str(data["amount"]))
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return jsonify(error="amount must be positive"), 400

    contribution = SavingsContribution(
        goal_id=goal_id,
        user_id=uid,
        amount=amount,
        notes=data.get("notes"),
    )
    goal.current_amount = (goal.current_amount or 0) + amount
    goal.is_completed = goal.current_amount >= goal.target_amount
    db.session.add(contribution)
    db.session.commit()
    logger.info("User %s added %s to goal %s (now %s/%s)", uid, amount, goal.name, goal.current_amount, goal.target_amount)
    return jsonify(
        contribution={
            "id": contribution.id,
            "amount": str(contribution.amount),
            "notes": contribution.notes,
            "created_at": contribution.created_at.isoformat(),
        },
        goal=_serialize_goal(goal),
    ), 201


@bp.delete("/<int:goal_id>/contributions/<int:contribution_id>")
@jwt_required()
def delete_contribution(goal_id, contribution_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    c = db.session.query(SavingsContribution).filter_by(id=contribution_id, goal_id=goal_id, user_id=uid).first()
    if not c:
        return jsonify(error="contribution not found"), 404
    goal.current_amount = (goal.current_amount or 0) - c.amount
    if goal.current_amount < 0:
        goal.current_amount = 0
    goal.is_completed = goal.current_amount >= goal.target_amount
    db.session.delete(c)
    db.session.commit()
    return jsonify(goal=_serialize_goal(goal))
