"""Goal-based savings tracking & milestones REST endpoints.

Endpoints
---------
POST   /goals                  – Create a new savings goal
GET    /goals                  – List all goals for the user
GET    /goals/<id>             – Get goal details with contributions & milestones
PUT    /goals/<id>             – Update goal metadata
DELETE /goals/<id>             – Cancel / delete a goal
POST   /goals/<id>/contribute  – Add a contribution to a goal
GET    /goals/<id>/milestones  – List milestones for a goal
GET    /goals/summary          – Overview: total saved, active goals, progress
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
import logging

from ..extensions import db
from ..models import (
    SavingsGoal, GoalContribution, GoalMilestone,
    GoalStatus, MILESTONE_DEFAULTS,
)

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")


def _goal_dict(g, include_details=False):
    d = {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "status": g.status,
        "progress_pct": g.progress_pct,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "icon": g.icon,
        "color": g.color,
        "created_at": g.created_at.isoformat(),
        "completed_at": g.completed_at.isoformat() if g.completed_at else None,
    }
    if include_details:
        d["contributions"] = [
            {
                "id": c.id,
                "amount": float(c.amount),
                "notes": c.notes,
                "contributed_at": c.contributed_at.isoformat(),
            }
            for c in g.contributions.order_by(
                GoalContribution.contributed_at.desc()
            ).all()
        ]
        d["milestones"] = [
            {
                "id": m.id,
                "percentage": m.percentage,
                "title": m.title,
                "reached": m.reached_at is not None,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in g.milestones.order_by(GoalMilestone.percentage).all()
        ]
    return d


def _check_milestones(goal):
    """Check and mark any newly reached milestones. Returns list of newly
    reached milestones."""
    newly_reached = []
    for ms in goal.milestones.filter(GoalMilestone.reached_at.is_(None)).all():
        if goal.progress_pct >= ms.percentage:
            ms.reached_at = datetime.utcnow()
            newly_reached.append({
                "percentage": ms.percentage,
                "title": ms.title,
            })
    # Auto-complete goal when 100% reached
    if goal.progress_pct >= 100 and goal.status == GoalStatus.ACTIVE.value:
        goal.status = GoalStatus.COMPLETED.value
        goal.completed_at = datetime.utcnow()
    return newly_reached


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    target = data.get("target_amount")
    if not name or target is None:
        return jsonify(error="name and target_amount required"), 400

    try:
        target = float(target)
        if target <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="target_amount must be a positive number"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target,
        currency=data.get("currency", "INR"),
        target_date=data.get("target_date"),
        icon=data.get("icon", "piggy-bank"),
        color=data.get("color", "#4F46E5"),
    )
    db.session.add(goal)
    db.session.flush()

    # Create default milestones
    for pct, title in MILESTONE_DEFAULTS:
        db.session.add(GoalMilestone(
            goal_id=goal.id, percentage=pct, title=title,
        ))
    db.session.commit()

    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, name)
    return jsonify(goal=_goal_dict(goal, include_details=True)), 201


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")

    query = SavingsGoal.query.filter_by(user_id=uid)
    if status_filter:
        query = query.filter_by(status=status_filter.upper())
    query = query.order_by(SavingsGoal.created_at.desc())

    goals = query.all()
    return jsonify(goals=[_goal_dict(g) for g in goals]), 200


@bp.get("/summary")
@jwt_required()
def goals_summary():
    uid = int(get_jwt_identity())
    goals = SavingsGoal.query.filter_by(user_id=uid).all()

    active = [g for g in goals if g.status == GoalStatus.ACTIVE.value]
    completed = [g for g in goals if g.status == GoalStatus.COMPLETED.value]

    total_saved = sum(float(g.current_amount) for g in goals)
    total_target = sum(float(g.target_amount) for g in active)
    active_saved = sum(float(g.current_amount) for g in active)

    return jsonify(summary={
        "total_goals": len(goals),
        "active_goals": len(active),
        "completed_goals": len(completed),
        "total_saved": round(total_saved, 2),
        "active_target": round(total_target, 2),
        "active_saved": round(active_saved, 2),
        "overall_progress_pct": (
            round(active_saved / total_target * 100, 1) if total_target > 0 else 0
        ),
    }), 200


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    return jsonify(goal=_goal_dict(goal, include_details=True)), 200


@bp.put("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        try:
            goal.target_amount = float(data["target_amount"])
        except (ValueError, TypeError):
            return jsonify(error="invalid target_amount"), 400
    if "target_date" in data:
        goal.target_date = data["target_date"]
    if "icon" in data:
        goal.icon = data["icon"]
    if "color" in data:
        goal.color = data["color"]
    if "status" in data:
        new_status = data["status"].upper()
        if new_status in [s.value for s in GoalStatus]:
            goal.status = new_status
            if new_status == GoalStatus.COMPLETED.value and not goal.completed_at:
                goal.completed_at = datetime.utcnow()

    db.session.commit()
    return jsonify(goal=_goal_dict(goal)), 200


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="goal deleted"), 200


# ------------------------------------------------------------------
# Contributions
# ------------------------------------------------------------------

@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    if goal.status != GoalStatus.ACTIVE.value:
        return jsonify(error="can only contribute to active goals"), 400

    data = request.get_json(silent=True) or {}
    amount = data.get("amount")
    if amount is None:
        return jsonify(error="amount required"), 400
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="amount must be a positive number"), 400

    contribution = GoalContribution(
        goal_id=goal.id,
        user_id=uid,
        amount=amount,
        notes=data.get("notes"),
    )
    db.session.add(contribution)
    goal.current_amount = float(goal.current_amount) + amount

    newly_reached = _check_milestones(goal)
    db.session.commit()

    logger.info("Contribution id=%s goal=%s amount=%s user=%s",
                contribution.id, goal.id, amount, uid)

    return jsonify(
        contribution={
            "id": contribution.id,
            "amount": float(contribution.amount),
            "notes": contribution.notes,
        },
        goal=_goal_dict(goal),
        milestones_reached=newly_reached,
    ), 201


# ------------------------------------------------------------------
# Milestones
# ------------------------------------------------------------------

@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id):
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    milestones = goal.milestones.order_by(GoalMilestone.percentage).all()
    return jsonify(milestones=[
        {
            "id": m.id,
            "percentage": m.percentage,
            "title": m.title,
            "reached": m.reached_at is not None,
            "reached_at": m.reached_at.isoformat() if m.reached_at else None,
        }
        for m in milestones
    ]), 200
