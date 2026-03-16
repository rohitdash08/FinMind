from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress_pct = round((current / target * 100), 2) if target > 0 else 0.0
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "progress_pct": progress_pct,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "created_at": g.created_at.isoformat(),
    }


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
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or data.get("target_amount") is None:
        return jsonify(error="name and target_amount are required"), 400
    try:
        target = float(data["target_amount"])
        if target <= 0:
            raise ValueError("target_amount must be positive")
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="deadline must be ISO date (YYYY-MM-DD)"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=target,
        current_amount=float(data.get("current_amount", 0)),
        deadline=deadline,
        status=SavingsGoalStatus.ACTIVE.value,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, goal.name)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal))


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
    if "target_amount" in data:
        try:
            val = float(data["target_amount"])
            if val <= 0:
                raise ValueError("target_amount must be positive")
            goal.target_amount = val
        except (ValueError, TypeError) as e:
            return jsonify(error=str(e)), 400
    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="deadline must be ISO date (YYYY-MM-DD)"), 400
    if "status" in data:
        try:
            goal.status = SavingsGoalStatus(data["status"]).value
        except ValueError:
            return jsonify(error=f"invalid status: {data['status']}"), 400
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    try:
        amount = float(data.get("amount", 0))
        if amount <= 0:
            raise ValueError("amount must be positive")
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400

    goal.current_amount = float(goal.current_amount) + amount
    # Auto-complete if target reached
    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = SavingsGoalStatus.COMPLETED.value
    db.session.commit()
    logger.info(
        "Contribution to goal id=%s user=%s amount=%s new_total=%s",
        goal.id,
        uid,
        amount,
        goal.current_amount,
    )
    return jsonify(_goal_to_dict(goal))
