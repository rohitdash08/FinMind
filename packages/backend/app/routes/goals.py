"""Savings goals routes — track and manage savings milestones."""

from datetime import date
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal
import logging

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")


def _serialize(g: SavingsGoal) -> dict:
    progress = (
        round(float(g.current_amount) / float(g.target_amount) * 100, 1)
        if g.target_amount > 0
        else 0
    )
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": str(g.deadline) if g.deadline else None,
        "completed": g.completed,
        "progress_percent": progress,
        "created_at": g.created_at.isoformat(),
    }


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    target = data.get("target_amount")

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not target or float(target) <= 0:
        return jsonify({"error": "target_amount must be positive"}), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=Decimal(str(target)),
        current_amount=Decimal(str(data.get("current_amount", 0))),
        currency=data.get("currency", "USD"),
        deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(_serialize(goal)), 201


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = SavingsGoal.query.filter_by(user_id=uid).order_by(
        SavingsGoal.completed, SavingsGoal.created_at.desc()
    ).all()
    return jsonify([_serialize(g) for g in goals])


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first_or_404()
    return jsonify(_serialize(goal))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first_or_404()
    data = request.get_json(force=True)

    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        goal.target_amount = Decimal(str(data["target_amount"]))
    if "current_amount" in data:
        goal.current_amount = Decimal(str(data["current_amount"]))
    if "currency" in data:
        goal.currency = data["currency"]
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None

    # Auto-complete when target reached
    if goal.current_amount >= goal.target_amount:
        goal.completed = True

    db.session.commit()
    return jsonify(_serialize(goal))


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    """Add a contribution towards a savings goal."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first_or_404()
    data = request.get_json(force=True)
    amount = data.get("amount")

    if not amount or float(amount) <= 0:
        return jsonify({"error": "amount must be positive"}), 400

    goal.current_amount += Decimal(str(amount))
    if goal.current_amount >= goal.target_amount:
        goal.completed = True

    db.session.commit()
    return jsonify(_serialize(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first_or_404()
    db.session.delete(goal)
    db.session.commit()
    return jsonify({"message": "deleted"})
