from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, SavingsGoalStatus, User
from ..services.cache import cache_delete_patterns
from decimal import Decimal

bp = Blueprint("savings", __name__)


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
    return jsonify(
        [
            {
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "target_amount": float(g.target_amount),
                "current_amount": float(g.current_amount),
                "currency": g.currency,
                "start_date": g.start_date.isoformat() if g.start_date else None,
                "target_date": g.target_date.isoformat() if g.target_date else None,
                "status": g.status.value,
                "milestones": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "target_amount": float(m.target_amount),
                        "achieved": m.achieved,
                        "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
                    }
                    for m in g.milestones
                ],
                "progress_pct": round(float(g.current_amount) / float(g.target_amount) * 100, 2)
                if g.target_amount and g.target_amount > 0
                else 0,
                "created_at": g.created_at.isoformat(),
            }
            for g in goals
        ]
    )


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"],
        description=data.get("description", ""),
        target_amount=Decimal(str(data["target_amount"])),
        current_amount=Decimal(str(data.get("current_amount", 0))),
        currency=data.get("currency") or (user.preferred_currency if user and user.preferred_currency else "INR"),
        start_date=date.fromisoformat(data["start_date"]) if data.get("start_date") else date.today(),
        target_date=date.fromisoformat(data["target_date"]) if data.get("target_date") else None,
    )
    db.session.add(goal)
    db.session.commit()
    cache_delete_patterns([f"user:{uid}:*"])
    return jsonify(id=goal.id), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    return jsonify(
        {
            "id": goal.id,
            "name": goal.name,
            "description": goal.description,
            "target_amount": float(goal.target_amount),
            "current_amount": float(goal.current_amount),
            "currency": goal.currency,
            "start_date": goal.start_date.isoformat() if goal.start_date else None,
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
            "status": goal.status.value,
            "milestones": [
                {
                    "id": m.id,
                    "name": m.name,
                    "target_amount": float(m.target_amount),
                    "achieved": m.achieved,
                    "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
                }
                for m in goal.milestones
            ],
            "progress_pct": round(float(goal.current_amount) / float(goal.target_amount) * 100, 2)
            if goal.target_amount and goal.target_amount > 0
            else 0,
            "created_at": goal.created_at.isoformat(),
            "updated_at": goal.updated_at.isoformat(),
        }
    )


@bp.put("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        goal.name = data["name"]
    if "description" in data:
        goal.description = data["description"]
    if "target_amount" in data:
        goal.target_amount = Decimal(str(data["target_amount"]))
    if "current_amount" in data:
        goal.current_amount = Decimal(str(data["current_amount"]))
    if "target_date" in data:
        goal.target_date = date.fromisoformat(data["target_date"]) if data["target_date"] else None
    if "status" in data:
        goal.status = SavingsGoalStatus(data["status"])

    db.session.commit()
    cache_delete_patterns([f"user:{uid}:*"])
    return jsonify(message="updated")


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    db.session.delete(goal)
    db.session.commit()
    cache_delete_patterns([f"user:{uid}:*"])
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = Decimal(str(data.get("amount", 0)))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400

    goal.current_amount += amount

    # Auto-check milestones
    for milestone in goal.milestones:
        if not milestone.achieved and goal.current_amount >= milestone.target_amount:
            milestone.achieved = True
            milestone.achieved_at = date.today()

    db.session.commit()
    cache_delete_patterns([f"user:{uid}:*"])
    return jsonify(
        id=goal.id,
        current_amount=float(goal.current_amount),
        progress_pct=round(float(goal.current_amount) / float(goal.target_amount) * 100, 2)
        if goal.target_amount and goal.target_amount > 0
        else 0,
    )


# --- Milestone endpoints ---

@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def add_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    milestone = SavingsMilestone(
        savings_goal_id=goal_id,
        name=data["name"],
        target_amount=Decimal(str(data["target_amount"])),
    )
    db.session.add(milestone)
    db.session.commit()
    return jsonify(id=milestone.id), 201


@bp.put("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.savings_goal_id != goal_id:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        milestone.name = data["name"]
    if "target_amount" in data:
        milestone.target_amount = Decimal(str(data["target_amount"]))

    db.session.commit()
    return jsonify(message="updated")


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.savings_goal_id != goal_id:
        return jsonify(error="not found"), 404

    db.session.delete(milestone)
    db.session.commit()
    return jsonify(message="deleted")
