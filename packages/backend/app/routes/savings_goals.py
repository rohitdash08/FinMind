from datetime import date, datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")

MILESTONES = (25, 50, 75, 100)


def _goal_dict(g: SavingsGoal) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "currency": g.currency,
        "status": g.status if isinstance(g.status, str) else g.status.value,
        "achieved_milestones": g.achieved_milestones(),
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter:
        q = q.filter(SavingsGoal.status == status_filter)
    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings_goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or data.get("target_amount") is None:
        return jsonify(error="name and target_amount are required"), 400
    target = float(data["target_amount"])
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline format, use YYYY-MM-DD"), 400

    current = float(data.get("current_amount", 0))
    if current < 0:
        return jsonify(error="current_amount cannot be negative"), 400

    status = SavingsGoalStatus.ACTIVE
    if current >= target:
        status = SavingsGoalStatus.COMPLETED

    g = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=target,
        current_amount=current,
        deadline=deadline,
        currency=data.get("currency", "USD"),
        status=status.value,
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created savings_goal id=%s user=%s name=%s", g.id, uid, g.name)
    return jsonify(_goal_dict(g)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_dict(g))


@bp.put("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        g.name = data["name"]
    if "target_amount" in data:
        target = float(data["target_amount"])
        if target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        g.target_amount = target
    if "current_amount" in data:
        current = float(data["current_amount"])
        if current < 0:
            return jsonify(error="current_amount cannot be negative"), 400
        g.current_amount = current
    if "deadline" in data:
        if data["deadline"] is None:
            g.deadline = None
        else:
            try:
                g.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline format, use YYYY-MM-DD"), 400
    if "currency" in data:
        g.currency = data["currency"]
    if "status" in data:
        try:
            g.status = SavingsGoalStatus(data["status"]).value
        except ValueError:
            return jsonify(error="invalid status"), 400

    # Auto-complete when current_amount reaches target
    current_status = g.status if isinstance(g.status, str) else g.status.value
    if (
        current_status == SavingsGoalStatus.ACTIVE.value
        and float(g.current_amount) >= float(g.target_amount)
    ):
        g.status = SavingsGoalStatus.COMPLETED.value

    g.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated savings_goal id=%s user=%s", g.id, uid)
    return jsonify(_goal_dict(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    g.status = SavingsGoalStatus.CANCELLED.value
    db.session.commit()
    logger.info("Deleted savings_goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")


@bp.get("/<int:goal_id>/progress")
@jwt_required()
def goal_progress(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404

    target = float(g.target_amount)
    current = float(g.current_amount)
    percentage_complete = round((current / target * 100) if target > 0 else 0, 2)
    remaining_amount = round(max(target - current, 0), 2)

    days_left = None
    on_track = None
    if g.deadline:
        today = date.today()
        days_left = (g.deadline - today).days
        if days_left <= 0:
            on_track = current >= target
        else:
            total_days = (g.deadline - g.created_at.date()).days
            if total_days > 0:
                days_elapsed = (today - g.created_at.date()).days
                expected_pct = days_elapsed / total_days
                actual_pct = current / target if target > 0 else 0
                on_track = actual_pct >= expected_pct
            else:
                on_track = current >= target

    return jsonify(
        {
            "id": g.id,
            "name": g.name,
            "target_amount": target,
            "current_amount": current,
            "percentage_complete": percentage_complete,
            "remaining_amount": remaining_amount,
            "days_left": days_left,
            "on_track": on_track,
            "achieved_milestones": g.achieved_milestones(),
            "status": g.status if isinstance(g.status, str) else g.status.value,
        }
    )
