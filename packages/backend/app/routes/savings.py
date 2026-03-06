from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _goal_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "color": g.color,
        "active": g.active,
        "progress": round(current / target * 100, 1) if target > 0 else 0,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    active_only = request.args.get("active", "true").lower() == "true"
    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if active_only:
        query = query.filter_by(active=True)
    goals = query.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    if not data.get("name") or not data.get("target_amount"):
        return jsonify({"error": "name and target_amount are required"}), 400
    g = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=data["target_amount"],
        current_amount=data.get("current_amount", 0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        target_date=date.fromisoformat(data["target_date"]) if data.get("target_date") else None,
        color=data.get("color", "#3B82F6"),
    )
    db.session.add(g)
    db.session.commit()
    cache_delete_patterns(f"user:{uid}:*")
    logger.info("Created savings goal id=%s user=%s", g.id, uid)
    return jsonify(_goal_dict(g)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not g:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(_goal_dict(g))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not g:
        return jsonify({"error": "Goal not found"}), 404
    data = request.get_json() or {}
    if "name" in data:
        g.name = data["name"]
    if "target_amount" in data:
        g.target_amount = data["target_amount"]
    if "currency" in data:
        g.currency = data["currency"]
    if "target_date" in data:
        g.target_date = date.fromisoformat(data["target_date"]) if data["target_date"] else None
    if "color" in data:
        g.color = data["color"]
    if "active" in data:
        g.active = bool(data["active"])
    db.session.commit()
    cache_delete_patterns(f"user:{uid}:*")
    logger.info("Updated savings goal id=%s user=%s", g.id, uid)
    return jsonify(_goal_dict(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not g:
        return jsonify({"error": "Goal not found"}), 404
    db.session.delete(g)
    db.session.commit()
    cache_delete_patterns(f"user:{uid}:*")
    logger.info("Deleted savings goal id=%s user=%s", g.id, uid)
    return jsonify({"message": "Goal deleted"})


# ── Contributions ────────────────────────────────────────────────


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not g:
        return jsonify({"error": "Goal not found"}), 404
    contributions = (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsContribution.contributed_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": c.id,
                "amount": float(c.amount),
                "notes": c.notes,
                "contributed_at": c.contributed_at.isoformat(),
            }
            for c in contributions
        ]
    )


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()
    if not g:
        return jsonify({"error": "Goal not found"}), 404
    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify({"error": "amount must be positive"}), 400
    c = SavingsContribution(
        goal_id=goal_id,
        amount=amount,
        notes=data.get("notes"),
        contributed_at=date.fromisoformat(data["contributed_at"]) if data.get("contributed_at") else date.today(),
    )
    db.session.add(c)
    g.current_amount = float(g.current_amount) + float(amount)
    db.session.commit()
    cache_delete_patterns(f"user:{uid}:*")
    logger.info("Contribution goal=%s amount=%s user=%s", goal_id, amount, uid)
    return jsonify({
        "contribution": {
            "id": c.id,
            "amount": float(c.amount),
            "notes": c.notes,
            "contributed_at": c.contributed_at.isoformat(),
        },
        "goal": _goal_dict(g),
    }), 201
