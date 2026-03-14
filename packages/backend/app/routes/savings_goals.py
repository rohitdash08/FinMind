from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")

# Milestone thresholds (percentage of target)
MILESTONES = [25, 50, 75, 100]


def _goal_json(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    pct = round((current / target) * 100, 1) if target > 0 else 0
    achieved = [m for m in MILESTONES if pct >= m]
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "icon": g.icon,
        "active": g.active,
        "progress_pct": pct,
        "milestones_achieved": achieved,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    include_completed = request.args.get("include_completed", "false").lower() == "true"
    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if not include_completed:
        query = query.filter_by(active=True)
    items = query.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_json(g) for g in items])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    if not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount are required"), 400
    target = float(data["target_amount"])
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400
    g = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=target,
        current_amount=float(data.get("current_amount", 0)),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        target_date=date.fromisoformat(data["target_date"]) if data.get("target_date") else None,
        icon=data.get("icon", "piggy-bank"),
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", g.id, uid, g.name)
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(_goal_json(g)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_json(g))


@bp.patch("/<int:goal_id>")
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
        val = float(data["target_amount"])
        if val <= 0:
            return jsonify(error="target_amount must be positive"), 400
        g.target_amount = val
    if "target_date" in data:
        g.target_date = date.fromisoformat(data["target_date"]) if data["target_date"] else None
    if "icon" in data:
        g.icon = data["icon"]
    if "active" in data:
        g.active = bool(data["active"])
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", g.id, uid)
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(_goal_json(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(g)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", g.id, uid)
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if not data.get("amount"):
        return jsonify(error="amount is required"), 400
    amt = float(data["amount"])
    if amt <= 0:
        return jsonify(error="amount must be positive"), 400

    c = SavingsContribution(
        goal_id=goal_id,
        amount=amt,
        notes=data.get("notes"),
        contributed_at=date.fromisoformat(data["contributed_at"]) if data.get("contributed_at") else date.today(),
    )
    db.session.add(c)
    g.current_amount = float(g.current_amount) + amt
    db.session.commit()
    logger.info(
        "Contribution id=%s goal=%s amount=%s new_total=%s",
        c.id, goal_id, amt, float(g.current_amount),
    )
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])

    # Check if a new milestone was reached
    pct = round((float(g.current_amount) / float(g.target_amount)) * 100, 1) if float(g.target_amount) > 0 else 0
    new_milestones = [m for m in MILESTONES if pct >= m and pct - (amt / float(g.target_amount) * 100) < m]

    return jsonify(
        contribution={
            "id": c.id,
            "amount": float(c.amount),
            "notes": c.notes,
            "contributed_at": c.contributed_at.isoformat(),
        },
        goal=_goal_json(g),
        new_milestones=new_milestones,
    ), 201


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsContribution.contributed_at.desc())
        .all()
    )
    return jsonify([
        {
            "id": c.id,
            "amount": float(c.amount),
            "notes": c.notes,
            "contributed_at": c.contributed_at.isoformat(),
        }
        for c in items
    ])


@bp.post("/<int:goal_id>/withdraw")
@jwt_required()
def withdraw(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if not data.get("amount"):
        return jsonify(error="amount is required"), 400
    amt = float(data["amount"])
    if amt <= 0:
        return jsonify(error="amount must be positive"), 400
    if amt > float(g.current_amount):
        return jsonify(error="insufficient balance"), 400

    c = SavingsContribution(
        goal_id=goal_id,
        amount=-amt,
        notes=data.get("notes", "Withdrawal"),
        contributed_at=date.fromisoformat(data["contributed_at"]) if data.get("contributed_at") else date.today(),
    )
    db.session.add(c)
    g.current_amount = float(g.current_amount) - amt
    db.session.commit()
    logger.info(
        "Withdrawal id=%s goal=%s amount=%s new_total=%s",
        c.id, goal_id, amt, float(g.current_amount),
    )
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
    return jsonify(
        contribution={
            "id": c.id,
            "amount": float(c.amount),
            "notes": c.notes,
            "contributed_at": c.contributed_at.isoformat(),
        },
        goal=_goal_json(g),
    )
