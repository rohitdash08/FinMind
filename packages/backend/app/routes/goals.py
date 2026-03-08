from datetime import date
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import SavingsGoal

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")


def _goal_to_dict(goal: SavingsGoal):
    target = float(goal.target_amount or 0)
    current = float(goal.current_amount or 0)
    progress = round((current / target) * 100, 2) if target > 0 else 0.0

    milestones = []
    for pct in (25, 50, 75, 100):
        milestones.append(
            {
                "percent": pct,
                "amount": round((target * pct) / 100.0, 2),
                "reached": progress >= pct,
            }
        )

    return {
        "id": goal.id,
        "title": goal.title,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "progress_pct": progress,
        "milestones": milestones,
        "created_at": goal.created_at.isoformat() + "Z",
        "updated_at": goal.updated_at.isoformat() + "Z",
    }


@bp.post("")
@jwt_required()
def create_goal():
    user_id = int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}

    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400

    try:
        target_amount = float(payload.get("target_amount"))
    except (TypeError, ValueError):
        return jsonify(error="target_amount must be numeric"), 400

    if target_amount <= 0:
        return jsonify(error="target_amount must be > 0"), 400

    current_amount = float(payload.get("current_amount") or 0)
    currency = (payload.get("currency") or "INR").strip().upper()[:10]

    target_date = None
    if payload.get("target_date"):
        try:
            target_date = date.fromisoformat(payload.get("target_date"))
        except ValueError:
            return jsonify(error="target_date must be YYYY-MM-DD"), 400

    goal = SavingsGoal(
        user_id=user_id,
        title=title,
        target_amount=target_amount,
        current_amount=current_amount,
        currency=currency,
        target_date=target_date,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Savings goal created user_id=%s title=%s", user_id, title)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("")
@jwt_required()
def list_goals():
    user_id = int(get_jwt_identity())
    rows = (
        db.session.query(SavingsGoal)
        .filter(SavingsGoal.user_id == user_id)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("Savings goals listed user_id=%s count=%s", user_id, len(rows))
    return jsonify([_goal_to_dict(row) for row in rows])


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    user_id = int(get_jwt_identity())
    goal = (
        db.session.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id)
        .first()
    )
    if not goal:
        return jsonify(error="goal not found"), 404

    payload = request.get_json(silent=True) or {}
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify(error="title cannot be empty"), 400
        goal.title = title

    if "target_amount" in payload:
        try:
            v = float(payload.get("target_amount"))
        except (TypeError, ValueError):
            return jsonify(error="target_amount must be numeric"), 400
        if v <= 0:
            return jsonify(error="target_amount must be > 0"), 400
        goal.target_amount = v

    if "current_amount" in payload:
        try:
            goal.current_amount = float(payload.get("current_amount"))
        except (TypeError, ValueError):
            return jsonify(error="current_amount must be numeric"), 400

    if "currency" in payload:
        goal.currency = (payload.get("currency") or "INR").strip().upper()[:10]

    if "target_date" in payload:
        td = payload.get("target_date")
        if td in (None, ""):
            goal.target_date = None
        else:
            try:
                goal.target_date = date.fromisoformat(td)
            except ValueError:
                return jsonify(error="target_date must be YYYY-MM-DD"), 400

    db.session.commit()
    logger.info("Savings goal updated user_id=%s goal_id=%s", user_id, goal_id)
    return jsonify(_goal_to_dict(goal))
