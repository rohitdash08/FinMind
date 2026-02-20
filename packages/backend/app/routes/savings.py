from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone

bp = Blueprint("savings", __name__)

MILESTONE_PERCENTAGES = [
    (25, "25% milestone"),
    (50, "50% milestone"),
    (75, "75% milestone"),
    (100, "100% – Goal reached!"),
]


def _goal_to_dict(goal: SavingsGoal) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    progress = (current / target * 100) if target > 0 else 0
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "progress_pct": round(progress, 2),
        "created_at": goal.created_at.isoformat(),
    }


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "name": m.name,
        "amount": float(m.amount),
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
    }


def _create_milestones(goal: SavingsGoal) -> None:
    """Create milestone records for a goal at 25/50/75/100%."""
    for pct, label in MILESTONE_PERCENTAGES:
        amount = goal.target_amount * pct / 100
        ms = SavingsMilestone(goal_id=goal.id, name=label, amount=amount)
        db.session.add(ms)


def _check_milestones(goal: SavingsGoal) -> None:
    """Mark milestones as reached when current_amount meets them."""
    for ms in goal.milestones:
        if ms.reached_at is None and goal.current_amount >= ms.amount:
            ms.reached_at = datetime.utcnow()


@bp.route("/goals", methods=["POST"])
@jwt_required()
def create_goal():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name or not str(name).strip():
        return jsonify(error="name is required"), 400

    try:
        target_amount = Decimal(str(data["target_amount"]))
        if target_amount <= 0:
            raise ValueError
    except (KeyError, ValueError, InvalidOperation):
        return jsonify(error="target_amount must be a positive number"), 400

    current_amount = Decimal("0")
    if "current_amount" in data:
        try:
            current_amount = Decimal(str(data["current_amount"]))
            if current_amount < 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            return jsonify(error="current_amount must be a non-negative number"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify(error="deadline must be YYYY-MM-DD"), 400

    user_id = get_jwt_identity()
    goal = SavingsGoal(
        user_id=user_id,
        name=str(name).strip(),
        target_amount=target_amount,
        current_amount=current_amount,
        currency=data.get("currency", "INR"),
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.flush()  # get goal.id
    _create_milestones(goal)
    _check_milestones(goal)
    db.session.commit()
    return jsonify(_goal_to_dict(goal)), 201


@bp.route("/goals", methods=["GET"])
@jwt_required()
def list_goals():
    user_id = get_jwt_identity()
    goals = SavingsGoal.query.filter_by(user_id=user_id).order_by(SavingsGoal.created_at.desc()).all()
    return jsonify([_goal_to_dict(g) for g in goals]), 200


@bp.route("/goals/<int:goal_id>", methods=["PUT", "PATCH"])
@jwt_required()
def update_goal(goal_id: int):
    user_id = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        if not str(data["name"]).strip():
            return jsonify(error="name cannot be empty"), 400
        goal.name = str(data["name"]).strip()

    if "target_amount" in data:
        try:
            val = Decimal(str(data["target_amount"]))
            if val <= 0:
                raise ValueError
            goal.target_amount = val
            # Recreate milestones with new target
            SavingsMilestone.query.filter_by(goal_id=goal.id).delete()
            db.session.flush()
            _create_milestones(goal)
        except (ValueError, InvalidOperation):
            return jsonify(error="target_amount must be a positive number"), 400

    if "current_amount" in data:
        try:
            val = Decimal(str(data["current_amount"]))
            if val < 0:
                raise ValueError
            goal.current_amount = val
        except (ValueError, InvalidOperation):
            return jsonify(error="current_amount must be a non-negative number"), 400

    if "add_funds" in data:
        try:
            val = Decimal(str(data["add_funds"]))
            if val <= 0:
                raise ValueError
            goal.current_amount = goal.current_amount + val
        except (ValueError, InvalidOperation):
            return jsonify(error="add_funds must be a positive number"), 400

    if "currency" in data:
        goal.currency = data["currency"]

    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify(error="deadline must be YYYY-MM-DD"), 400

    _check_milestones(goal)
    db.session.commit()
    return jsonify(_goal_to_dict(goal)), 200


@bp.route("/goals/<int:goal_id>", methods=["DELETE"])
@jwt_required()
def delete_goal(goal_id: int):
    user_id = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="goal deleted"), 200


@bp.route("/goals/<int:goal_id>/milestones", methods=["GET"])
@jwt_required()
def get_milestones(goal_id: int):
    user_id = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    milestones = SavingsMilestone.query.filter_by(goal_id=goal_id).order_by(SavingsMilestone.amount).all()
    return jsonify([_milestone_to_dict(m) for m in milestones]), 200
