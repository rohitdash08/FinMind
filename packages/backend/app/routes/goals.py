from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Goal, GoalMilestone, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")


def _goal_dict(g: Goal) -> dict:
    return {
        "id": g.id,
        "title": g.title,
        "description": g.description,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "icon": g.icon,
        "active": g.active,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _milestone_dict(m: GoalMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "label": m.label,
        "target_amount": float(m.target_amount),
        "reached": m.reached,
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Goal)
        .filter_by(user_id=uid, active=True)
        .order_by(Goal.created_at.desc())
        .all()
    )
    logger.info("List goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_dict(g) for g in items])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    deadline = None
    if data.get("deadline"):
        deadline = date.fromisoformat(data["deadline"])
    g = Goal(
        user_id=uid,
        title=data["title"],
        description=data.get("description"),
        target_amount=data["target_amount"],
        current_amount=data.get("current_amount", 0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline,
        icon=data.get("icon"),
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created goal id=%s user=%s title=%s", g.id, uid, g.title)
    cache_delete_patterns([f"user:{uid}:goals*"])
    return jsonify(id=g.id), 201


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(Goal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    for field in ("title", "description", "icon"):
        if field in data:
            setattr(g, field, data[field])
    if "target_amount" in data:
        g.target_amount = data["target_amount"]
    if "current_amount" in data:
        g.current_amount = data["current_amount"]
    if "currency" in data:
        g.currency = data["currency"]
    if "active" in data:
        g.active = bool(data["active"])
    if "deadline" in data:
        g.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None
    db.session.commit()
    logger.info("Updated goal id=%s user=%s", g.id, uid)
    cache_delete_patterns([f"user:{uid}:goals*"])
    return jsonify(message="updated")


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(Goal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    g.active = False
    db.session.commit()
    logger.info("Deleted goal id=%s user=%s", g.id, uid)
    cache_delete_patterns([f"user:{uid}:goals*"])
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(Goal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    amount = data.get("amount", 0)
    g.current_amount = float(g.current_amount) + float(amount)
    db.session.commit()
    logger.info("Contributed goal id=%s user=%s amount=%s", g.id, uid, amount)
    cache_delete_patterns([f"user:{uid}:goals*"])
    return jsonify(current_amount=float(g.current_amount))


@bp.get("/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(Goal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        db.session.query(GoalMilestone)
        .filter_by(goal_id=goal_id)
        .order_by(GoalMilestone.target_amount)
        .all()
    )
    return jsonify([_milestone_dict(m) for m in items])


@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def create_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(Goal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    m = GoalMilestone(
        goal_id=goal_id,
        label=data["label"],
        target_amount=data["target_amount"],
    )
    db.session.add(m)
    db.session.commit()
    logger.info("Created milestone id=%s goal_id=%s", m.id, goal_id)
    return jsonify(id=m.id), 201


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(Goal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    m = db.session.get(GoalMilestone, milestone_id)
    if not m or m.goal_id != goal_id:
        return jsonify(error="not found"), 404
    db.session.delete(m)
    db.session.commit()
    logger.info("Deleted milestone id=%s goal_id=%s", milestone_id, goal_id)
    return jsonify(message="deleted")
