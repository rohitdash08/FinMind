from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models_savings import SavingsGoal, SavingsMilestone

bp = Blueprint("goals", __name__)

_MILESTONE_PCTS = [25, 50, 75, 100]


def _sync_milestones(goal: SavingsGoal) -> None:
    existing = {m.percentage: m for m in goal.milestones}
    for pct in _MILESTONE_PCTS:
        threshold = float(goal.target_amount) * pct / 100
        reached = float(goal.current_amount) >= threshold
        if pct in existing:
            ms = existing[pct]
            if reached and not ms.reached_at:
                ms.reached_at = datetime.utcnow()
        else:
            ms = SavingsMilestone(
                goal_id=goal.id,
                percentage=pct,
                threshold_amount=threshold,
                reached_at=datetime.utcnow() if reached else None,
            )
            db.session.add(ms)
    db.session.commit()


@bp.get("")
@jwt_required()
def list_goals():
    uid = get_jwt_identity()
    goals = (
        SavingsGoal.query.filter_by(user_id=uid, deleted=False)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return jsonify([g.to_dict() for g in goals]), 200


@bp.post("")
@jwt_required()
def create_goal():
    uid = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        target = float(data["target_amount"])
        if target <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "target_amount must be a positive number"}), 400
    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.fromisoformat(data["deadline"]).date()
        except ValueError:
            return jsonify({"error": "deadline must be ISO date YYYY-MM-DD"}), 400
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        description=data.get("description", ""),
        icon=data.get("icon", "🎯"),
        target_amount=target,
        current_amount=float(data.get("current_amount", 0)),
        currency=data.get("currency", "INR"),
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()
    _sync_milestones(goal)
    return jsonify(goal.to_dict()), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(
        id=goal_id, user_id=uid, deleted=False
    ).first_or_404()
    return jsonify(goal.to_dict()), 200


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(
        id=goal_id, user_id=uid, deleted=False
    ).first_or_404()
    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        goal.name = name
    if "description" in data:
        goal.description = data["description"]
    if "target_amount" in data:
        try:
            t = float(data["target_amount"])
            if t <= 0:
                raise ValueError
            goal.target_amount = t
        except (ValueError, TypeError):
            return jsonify({"error": "target_amount must be a positive number"}), 400
    if "current_amount" in data:
        try:
            goal.current_amount = float(data["current_amount"])
        except (ValueError, TypeError):
            return jsonify({"error": "current_amount must be a number"}), 400
    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = datetime.fromisoformat(data["deadline"]).date()
            except ValueError:
                return jsonify({"error": "deadline must be ISO date YYYY-MM-DD"}), 400
    if "icon" in data:
        goal.icon = data["icon"]
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    _sync_milestones(goal)
    return jsonify(goal.to_dict()), 200


@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id: int):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(
        id=goal_id, user_id=uid, deleted=False
    ).first_or_404()
    data = request.get_json(silent=True) or {}
    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "amount must be a positive number"}), 400
    goal.current_amount = float(goal.current_amount) + amount
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    _sync_milestones(goal)
    return jsonify(goal.to_dict()), 200


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(
        id=goal_id, user_id=uid, deleted=False
    ).first_or_404()
    goal.deleted = True
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Goal deleted"}), 200


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(
        id=goal_id, user_id=uid, deleted=False
    ).first_or_404()
    return (
        jsonify(
            [m.to_dict() for m in sorted(goal.milestones, key=lambda m: m.percentage)]
        ),
        200,
    )
