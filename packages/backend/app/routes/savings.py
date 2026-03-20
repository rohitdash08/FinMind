from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _goal_json(g):
    progress = (
        float(g.current_amount) / float(g.target_amount) * 100
        if float(g.target_amount) > 0
        else 0
    )
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "achieved": g.achieved,
        "progress_pct": round(progress, 2),
        "created_at": g.created_at.isoformat(),
    }


def _contribution_json(c):
    return {
        "id": c.id,
        "goal_id": c.goal_id,
        "amount": float(c.amount),
        "notes": c.notes,
        "contributed_at": c.contributed_at.isoformat(),
    }


def _invalidate_cache(uid):
    cache_delete_patterns(
        [f"user:{uid}:savings_goals*", f"user:{uid}:dashboard_summary:*"]
    )


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_json(g) for g in items])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    g = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=data["target_amount"],
        current_amount=data.get("current_amount", 0),
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        target_date=(
            date.fromisoformat(data["target_date"]) if data.get("target_date") else None
        ),
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", g.id, uid, g.name)
    _invalidate_cache(uid)
    return jsonify(id=g.id), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    result = _goal_json(g)
    contributions = (
        g.contributions.order_by(SavingsContribution.contributed_at.desc()).all()
    )
    result["contributions"] = [_contribution_json(c) for c in contributions]
    return jsonify(result)


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
        g.target_amount = data["target_amount"]
    if "currency" in data:
        g.currency = data["currency"]
    if "target_date" in data:
        g.target_date = (
            date.fromisoformat(data["target_date"]) if data["target_date"] else None
        )
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", g.id, uid)
    _invalidate_cache(uid)
    return jsonify(_goal_json(g))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    # Delete contributions first, then goal
    SavingsContribution.query.filter_by(goal_id=g.id).delete()
    db.session.delete(g)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    _invalidate_cache(uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    amount = data["amount"]
    c = SavingsContribution(
        goal_id=g.id,
        user_id=uid,
        amount=amount,
        notes=data.get("notes"),
    )
    db.session.add(c)
    g.current_amount = float(g.current_amount) + float(amount)
    if float(g.current_amount) >= float(g.target_amount):
        g.achieved = True
    db.session.commit()
    logger.info(
        "Contribution id=%s goal=%s user=%s amount=%s achieved=%s",
        c.id,
        g.id,
        uid,
        amount,
        g.achieved,
    )
    _invalidate_cache(uid)
    return jsonify(
        id=c.id,
        current_amount=float(g.current_amount),
        achieved=g.achieved,
    ), 201


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        g.contributions.order_by(SavingsContribution.contributed_at.desc()).all()
    )
    logger.info(
        "List contributions goal=%s user=%s count=%s", goal_id, uid, len(items)
    )
    return jsonify([_contribution_json(c) for c in items])
