"""Savings goals routes."""

from datetime import datetime
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution

bp = Blueprint("savings", __name__)


@bp.get("/")
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
        goals=[_serialize_goal(g) for g in goals]
    )


@bp.post("/")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = data.get("name")
    target_amount = data.get("target_amount")
    if not name or not target_amount:
        return jsonify(error="name and target_amount required"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=Decimal(str(target_amount)),
        currency=data.get("currency", "INR"),
        target_date=_parse_date(data.get("target_date")),
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(goal=_serialize_goal(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404

    contributions = (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsContribution.created_at.desc())
        .all()
    )
    return jsonify(
        goal=_serialize_goal(goal),
        contributions=[_serialize_contribution(c) for c in contributions],
    )


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        goal.target_amount = Decimal(str(data["target_amount"]))
    if "target_date" in data:
        goal.target_date = _parse_date(data["target_date"])

    db.session.commit()
    return jsonify(goal=_serialize_goal(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted"), 200


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify(error="positive amount required"), 400

    contribution = SavingsContribution(
        goal_id=goal_id,
        amount=Decimal(str(amount)),
        notes=data.get("notes"),
    )
    db.session.add(contribution)

    goal.current_amount = Decimal(str(goal.current_amount)) + Decimal(str(amount))
    if goal.current_amount >= goal.target_amount and not goal.achieved:
        goal.achieved = True
        goal.achieved_at = datetime.utcnow()

    db.session.commit()
    return jsonify(
        goal=_serialize_goal(goal),
        contribution=_serialize_contribution(contribution),
    ), 201


def _serialize_goal(goal: SavingsGoal) -> dict:
    progress = (
        float(goal.current_amount) / float(goal.target_amount) * 100
        if float(goal.target_amount) > 0
        else 0
    )
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "progress_percent": round(min(progress, 100), 1),
        "achieved": goal.achieved,
        "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None,
        "created_at": goal.created_at.isoformat(),
    }


def _serialize_contribution(c: SavingsContribution) -> dict:
    return {
        "id": c.id,
        "amount": float(c.amount),
        "notes": c.notes,
        "created_at": c.created_at.isoformat(),
    }


def _parse_date(val):
    if not val:
        return None
    from datetime import date as date_type
    if isinstance(val, str):
        return date_type.fromisoformat(val)
    return val
