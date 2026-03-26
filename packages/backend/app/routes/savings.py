from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, SavingsContribution, User
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress = min((current / target) * 100, 100) if target > 0 else 0

    result = {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "icon": g.icon,
        "color": g.color,
        "status": g.status,
        "progress_pct": round(progress, 1),
        "remaining": round(max(target - current, 0), 2),
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }

    # Add days remaining if target_date is set and goal is active
    if g.target_date and g.status == SavingsGoalStatus.ACTIVE.value:
        days_left = (g.target_date - date.today()).days
        result["days_remaining"] = max(days_left, 0)
        # Monthly savings needed to hit target on time
        if days_left > 0:
            months_left = max(days_left / 30.0, 1)
            result["monthly_needed"] = round(
                float(max(target - current, 0)) / months_left, 2
            )
        else:
            result["monthly_needed"] = 0
    return result


def _contribution_to_dict(c: SavingsContribution) -> dict:
    return {
        "id": c.id,
        "goal_id": c.goal_id,
        "amount": float(c.amount),
        "note": c.note,
        "contributed_at": c.contributed_at.isoformat() if c.contributed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _invalidate_cache(uid: int):
    cache_delete_patterns(
        [f"user:{uid}:savings_goals*", f"user:{uid}:dashboard_summary:*"]
    )


# ── List all savings goals ──────────────────────────────────────────
@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status", "ACTIVE")

    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter and status_filter != "ALL":
        query = query.filter_by(status=status_filter)
    items = query.order_by(SavingsGoal.created_at.desc()).all()

    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_to_dict(g) for g in items])


# ── Get single goal with contributions ──────────────────────────────
@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404

    result = _goal_to_dict(g)
    contributions = (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsContribution.contributed_at.desc())
        .all()
    )
    result["contributions"] = [_contribution_to_dict(c) for c in contributions]
    return jsonify(result)


# ── Create a savings goal ───────────────────────────────────────────
@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    if not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount are required"), 400

    target_amount = Decimal(str(data["target_amount"]))
    if target_amount <= 0:
        return jsonify(error="target_amount must be positive"), 400

    g = SavingsGoal(
        user_id=uid,
        name=data["name"],
        description=data.get("description"),
        target_amount=target_amount,
        current_amount=Decimal(str(data.get("current_amount", 0))),
        currency=data.get("currency")
        or (user.preferred_currency if user else "INR"),
        target_date=(
            date.fromisoformat(data["target_date"])
            if data.get("target_date")
            else None
        ),
        icon=data.get("icon", "piggy-bank"),
        color=data.get("color", "#6366f1"),
    )
    db.session.add(g)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", g.id, uid, g.name)
    _invalidate_cache(uid)
    return jsonify(_goal_to_dict(g)), 201


# ── Update a savings goal ───────────────────────────────────────────
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
    if "description" in data:
        g.description = data["description"]
    if "target_amount" in data:
        g.target_amount = Decimal(str(data["target_amount"]))
    if "target_date" in data:
        g.target_date = (
            date.fromisoformat(data["target_date"]) if data["target_date"] else None
        )
    if "icon" in data:
        g.icon = data["icon"]
    if "color" in data:
        g.color = data["color"]
    if "status" in data and data["status"] in [s.value for s in SavingsGoalStatus]:
        g.status = data["status"]

    g.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", g.id, uid)
    _invalidate_cache(uid)
    return jsonify(_goal_to_dict(g))


# ── Delete a savings goal ───────────────────────────────────────────
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
    _invalidate_cache(uid)
    return jsonify(message="deleted")


# ── Add contribution to a goal ──────────────────────────────────────
@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    g = db.session.get(SavingsGoal, goal_id)
    if not g or g.user_id != uid:
        return jsonify(error="not found"), 404

    if g.status != SavingsGoalStatus.ACTIVE.value:
        return jsonify(error="goal is not active"), 400

    data = request.get_json() or {}
    if not data.get("amount"):
        return jsonify(error="amount is required"), 400

    amount = Decimal(str(data["amount"]))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400

    c = SavingsContribution(
        goal_id=goal_id,
        user_id=uid,
        amount=amount,
        note=data.get("note"),
        contributed_at=(
            date.fromisoformat(data["contributed_at"])
            if data.get("contributed_at")
            else date.today()
        ),
    )
    db.session.add(c)

    # Update goal's current_amount
    g.current_amount = g.current_amount + amount
    g.updated_at = datetime.utcnow()

    # Auto-complete if target reached
    if g.current_amount >= g.target_amount:
        g.status = SavingsGoalStatus.COMPLETED.value

    db.session.commit()
    logger.info(
        "Added contribution id=%s goal=%s user=%s amount=%s",
        c.id,
        goal_id,
        uid,
        amount,
    )
    _invalidate_cache(uid)
    return jsonify(
        {
            "contribution": _contribution_to_dict(c),
            "goal": _goal_to_dict(g),
        }
    ), 201


# ── Withdraw from a goal ────────────────────────────────────────────
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

    amount = Decimal(str(data["amount"]))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400
    if amount > g.current_amount:
        return jsonify(error="insufficient balance"), 400

    c = SavingsContribution(
        goal_id=goal_id,
        user_id=uid,
        amount=-amount,
        note=data.get("note", "Withdrawal"),
        contributed_at=date.today(),
    )
    db.session.add(c)

    g.current_amount = g.current_amount - amount
    g.updated_at = datetime.utcnow()

    # Re-activate if was completed and now below target
    if (
        g.status == SavingsGoalStatus.COMPLETED.value
        and g.current_amount < g.target_amount
    ):
        g.status = SavingsGoalStatus.ACTIVE.value

    db.session.commit()
    logger.info(
        "Withdrew from goal id=%s user=%s amount=%s", goal_id, uid, amount
    )
    _invalidate_cache(uid)
    return jsonify(
        {
            "contribution": _contribution_to_dict(c),
            "goal": _goal_to_dict(g),
        }
    )


# ── Savings summary / stats ─────────────────────────────────────────
@bp.get("/summary")
@jwt_required()
def summary():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .all()
    )

    active = [g for g in goals if g.status == SavingsGoalStatus.ACTIVE.value]
    completed = [g for g in goals if g.status == SavingsGoalStatus.COMPLETED.value]

    total_saved = sum(float(g.current_amount) for g in goals)
    total_target = sum(float(g.target_amount) for g in active)
    overall_progress = (
        round((total_saved / total_target) * 100, 1) if total_target > 0 else 0
    )

    return jsonify(
        {
            "total_goals": len(goals),
            "active_goals": len(active),
            "completed_goals": len(completed),
            "total_saved": round(total_saved, 2),
            "total_target": round(total_target, 2),
            "overall_progress_pct": overall_progress,
        }
    )
