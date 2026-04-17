"""Savings goals API routes"""
from datetime import date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution, SavingsMilestone, GoalStatus, User

bp = Blueprint("savings", __name__)


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status:
        try:
            q = q.filter_by(status=GoalStatus(status))
        except ValueError:
            pass
    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    return jsonify([g.to_dict() for g in goals])


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    result = goal.to_dict()
    result["milestones"] = [m.to_dict() for m in goal.milestones.all()]
    return jsonify(result)


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    try:
        target_amount = Decimal(str(data.get("target_amount", 0)))
        if target_amount <= 0:
            return jsonify(error="target_amount must be positive"), 400
    except (InvalidOperation, ValueError, TypeError):
        return jsonify(error="invalid target_amount"), 400
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline format"), 400
    goal = SavingsGoal(
        user_id=uid, name=name, target_amount=target_amount,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline, description=(data.get("description") or "").strip()[:500],
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(goal.to_dict()), 201


@bp.patch("/goals/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        goal.name = (data["name"] or "").strip()[:200]
    if "target_amount" in data:
        try:
            goal.target_amount = Decimal(str(data["target_amount"]))
        except (InvalidOperation, ValueError):
            return jsonify(error="invalid target_amount"), 400
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    if "description" in data:
        goal.description = (data["description"] or "")[:500]
    if "status" in data:
        goal.status = GoalStatus(data["status"])
    db.session.commit()
    return jsonify(goal.to_dict())


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="goal deleted"), 200


@bp.post("/goals/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    # Use row lock to prevent concurrent issues
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id).with_for_update().first()
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    if goal.status != GoalStatus.ACTIVE:
        return jsonify(error="cannot contribute to inactive goal"), 400
    data = request.get_json() or {}
    try:
        amount = Decimal(str(data.get("amount", 0)))
        if amount <= 0:
            return jsonify(error="amount must be positive"), 400
    except (InvalidOperation, ValueError, TypeError):
        return jsonify(error="invalid amount"), 400
    new_amount = min(goal.current_amount + amount, goal.target_amount)
    actual_contribution = new_amount - goal.current_amount
    goal.current_amount = new_amount
    if goal.is_completed():
        goal.status = GoalStatus.COMPLETED
    contribution = SavingsContribution(
        goal_id=goal_id, amount=actual_contribution, currency=goal.currency,
        note=(data.get("note") or "").strip()[:500],
    )
    db.session.add(contribution)
    achieved = goal.check_milestones()
    db.session.commit()
    result = goal.to_dict()
    result["contribution"] = contribution.to_dict()
    result["achieved_milestones"] = achieved
    return jsonify(result), 201


@bp.get("/goals/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    page = max(1, int(request.args.get("page", "1")))
    page_size = min(100, max(1, int(request.args.get("page_size", "50"))))
    contributions = db.session.query(SavingsContribution).filter_by(goal_id=goal_id).order_by(
        SavingsContribution.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return jsonify({"contributions": [c.to_dict() for c in contributions], "total": goal.contributions.count(), "page": page, "page_size": page_size})


@bp.get("/goals/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    return jsonify([m.to_dict() for m in goal.milestones.order_by(SavingsMilestone.percentage).all()])


@bp.post("/goals/<int:goal_id>/cancel")
@jwt_required()
def cancel_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="goal not found"), 404
    if goal.status != GoalStatus.ACTIVE:
        return jsonify(error="goal is not active"), 400
    goal.status = GoalStatus.CANCELLED
    db.session.commit()
    return jsonify(goal.to_dict())
