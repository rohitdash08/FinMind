from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import SavingsGoal

bp = Blueprint("goals", __name__)


def _goal_to_dict(g: SavingsGoal):
    target = float(g.target_amount or 0)
    current = float(g.current_amount or 0)
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
        "id": g.id,
        "title": g.title,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "progress_pct": progress,
        "milestones": milestones,
        "created_at": g.created_at.isoformat() + "Z",
        "updated_at": g.updated_at.isoformat() + "Z",
    }


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400

    try:
        target_amount = float(data.get("target_amount"))
    except (TypeError, ValueError):
        return jsonify(error="target_amount must be numeric"), 400

    if target_amount <= 0:
        return jsonify(error="target_amount must be > 0"), 400

    current_amount = float(data.get("current_amount") or 0)
    currency = (data.get("currency") or "INR").strip().upper()[:10]

    target_date = None
    if data.get("target_date"):
        try:
            target_date = date.fromisoformat(data.get("target_date"))
        except ValueError:
            return jsonify(error="target_date must be YYYY-MM-DD"), 400

    g = SavingsGoal(
        user_id=uid,
        title=title,
        target_amount=target_amount,
        current_amount=current_amount,
        currency=currency,
        target_date=target_date,
    )
    db.session.add(g)
    db.session.commit()
    return jsonify(_goal_to_dict(g)), 201


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(SavingsGoal)
        .filter(SavingsGoal.user_id == uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return jsonify([_goal_to_dict(r) for r in rows])


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = (
        db.session.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == uid)
        .first()
    )
    if not g:
        return jsonify(error="goal not found"), 404

    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify(error="title cannot be empty"), 400
        g.title = title

    if "target_amount" in data:
        try:
            v = float(data.get("target_amount"))
        except (TypeError, ValueError):
            return jsonify(error="target_amount must be numeric"), 400
        if v <= 0:
            return jsonify(error="target_amount must be > 0"), 400
        g.target_amount = v

    if "current_amount" in data:
        try:
            g.current_amount = float(data.get("current_amount"))
        except (TypeError, ValueError):
            return jsonify(error="current_amount must be numeric"), 400

    if "currency" in data:
        g.currency = (data.get("currency") or "INR").strip().upper()[:10]

    if "target_date" in data:
        td = data.get("target_date")
        if td in (None, ""):
            g.target_date = None
        else:
            try:
                g.target_date = date.fromisoformat(td)
            except ValueError:
                return jsonify(error="target_date must be YYYY-MM-DD"), 400

    db.session.commit()
    return jsonify(_goal_to_dict(g))
