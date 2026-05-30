from datetime import date, datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, GoalContribution, User
from decimal import Decimal, InvalidOperation
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("/goals")
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


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    target_amount = _parse_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="target_amount must be positive"), 400
    target_date = None
    if data.get("target_date"):
        try:
            target_date = date.fromisoformat(data["target_date"])
        except ValueError:
            return jsonify(error="invalid target_date"), 400
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        current_amount=0,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        target_date=target_date,
        icon=data.get("icon"),
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, name)
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
    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        goal.name = name
    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = target
    if "target_date" in data:
        if data["target_date"]:
            try:
                goal.target_date = date.fromisoformat(data["target_date"])
            except ValueError:
                return jsonify(error="invalid target_date"), 400
        else:
            goal.target_date = None
    if "icon" in data:
        goal.icon = data.get("icon")
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


@bp.post("/goals/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="amount must be positive"), 400
    contribution = GoalContribution(goal_id=goal.id, amount=amount)
    goal.current_amount = Decimal(str(goal.current_amount)) + amount
    db.session.add(contribution)
    db.session.commit()
    logger.info("Added contribution goal=%s amount=%s", goal_id, amount)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/goals/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    contributions = (
        db.session.query(GoalContribution)
        .filter_by(goal_id=goal_id)
        .order_by(GoalContribution.contributed_at.desc())
        .all()
    )
    return jsonify([
        {
            "id": c.id,
            "amount": float(c.amount),
            "contributed_at": c.contributed_at.isoformat(),
        }
        for c in contributions
    ])


@bp.get("/goals/<int:goal_id>/milestones")
@jwt_required()
def get_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_compute_milestones(goal))


def _goal_to_dict(goal: SavingsGoal) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    progress_pct = round((current / target) * 100, 2) if target > 0 else 0
    remaining = max(target - current, 0)
    days_left = None
    if goal.target_date:
        days_left = (goal.target_date - date.today()).days
    result = {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "icon": goal.icon,
        "progress_pct": progress_pct,
        "remaining": round(remaining, 2),
        "days_left": days_left,
        "created_at": goal.created_at.isoformat(),
    }
    return result


def _compute_milestones(goal: SavingsGoal) -> list[dict]:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    milestone_pcts = [25, 50, 75, 100]
    milestones = []
    for pct in milestone_pcts:
        amount = round(target * pct / 100, 2)
        reached = current >= amount
        milestones.append({
            "percentage": pct,
            "amount": amount,
            "reached": reached,
        })
    return milestones


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
