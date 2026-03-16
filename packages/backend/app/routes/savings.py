"""
Savings Goals routes — Goal-based savings tracking & milestones (Issue #133).

Endpoints:
  GET    /savings/goals              → list goals
  POST   /savings/goals              → create goal
  GET    /savings/goals/<id>         → get goal (with milestones + progress)
  PATCH  /savings/goals/<id>         → update goal (name, target, date, etc.)
  DELETE /savings/goals/<id>         → delete goal
  POST   /savings/goals/<id>/deposit → add/subtract amount (deposit or withdrawal)
  GET    /savings/goals/<id>/milestones         → list milestones
  POST   /savings/goals/<id>/milestones         → add milestone
  PATCH  /savings/goals/<id>/milestones/<mid>   → update milestone
  DELETE /savings/goals/<id>/milestones/<mid>   → delete milestone
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


# ─────────────────────────────────────────────────────────────────────────────
# Goals
# ─────────────────────────────────────────────────────────────────────────────


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="target_amount must be a positive number"), 400

    target_date = None
    if data.get("target_date"):
        try:
            target_date = date.fromisoformat(data["target_date"])
        except ValueError:
            return jsonify(error="invalid target_date (use YYYY-MM-DD)"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        description=(data.get("description") or "").strip() or None,
        target_amount=target,
        current_amount=Decimal("0"),
        currency=(data.get("currency") or "INR").upper()[:10],
        target_date=target_date,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s target=%s", goal.id, uid, name, target)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal, include_milestones=True))


@bp.patch("/goals/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        goal.name = name

    if "description" in data:
        goal.description = (data["description"] or "").strip() or None

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = target

    if "currency" in data:
        goal.currency = (data["currency"] or "INR").upper()[:10]

    if "target_date" in data:
        if data["target_date"] is None:
            goal.target_date = None
        else:
            try:
                goal.target_date = date.fromisoformat(data["target_date"])
            except ValueError:
                return jsonify(error="invalid target_date"), 400

    db.session.commit()
    return jsonify(_goal_to_dict(goal, include_milestones=True))


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/goals/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id: int):
    """
    Add or subtract an amount from current_amount.
    Positive amount = deposit. Negative amount = withdrawal.
    Automatically marks goal as achieved when current >= target.
    """
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="amount is required and must be a number"), 400
    if amount == Decimal("0"):
        return jsonify(error="amount must be non-zero (use a positive value to deposit, negative to withdraw)"), 400

    goal.current_amount = max(Decimal("0"), goal.current_amount + amount)

    # Check goal achievement — forward and reverse.
    newly_achieved = not goal.achieved and goal.current_amount >= goal.target_amount
    if newly_achieved:
        goal.achieved = True
    elif goal.achieved and goal.current_amount < goal.target_amount:
        # Withdrawal brought the balance back below the target: un-mark as achieved
        # so the flag accurately reflects current state.
        goal.achieved = False

    # Check milestones — forward and reverse.
    # Milestones are treated as live state (not immutable historical events): a
    # withdrawal that drops current_amount below a milestone's threshold resets
    # it so it can be re-earned.  If you prefer milestones to be permanent
    # records (e.g. "you once hit ₹5,000") simply remove the reverse block below.
    newly_achieved_milestones = []
    for m in goal.milestones:
        if not m.achieved and goal.current_amount >= m.target_amount:
            m.achieved = True
            m.achieved_at = datetime.utcnow()
            newly_achieved_milestones.append(m.name)
        elif m.achieved and goal.current_amount < m.target_amount:
            # Reversal: balance fell below this milestone's threshold.
            m.achieved = False
            m.achieved_at = None

    db.session.commit()

    result = _goal_to_dict(goal, include_milestones=True)
    result["newly_achieved"] = newly_achieved
    result["newly_achieved_milestones"] = newly_achieved_milestones
    logger.info("Deposit goal=%s user=%s amount=%s new_total=%s", goal_id, uid, amount, goal.current_amount)
    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# Milestones
# ─────────────────────────────────────────────────────────────────────────────


@bp.get("/goals/<int:goal_id>/milestones")
@jwt_required()
def list_milestones(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404
    return jsonify([_milestone_to_dict(m) for m in goal.milestones])


@bp.post("/goals/<int:goal_id>/milestones")
@jwt_required()
def create_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="target_amount must be positive"), 400

    if target > goal.target_amount:
        return jsonify(error="milestone target_amount cannot exceed goal target_amount"), 400

    milestone = SavingsMilestone(goal_id=goal_id, name=name, target_amount=target)

    # Auto-achieve if already reached
    if goal.current_amount >= target:
        milestone.achieved = True
        milestone.achieved_at = datetime.utcnow()

    db.session.add(milestone)
    db.session.commit()
    return jsonify(_milestone_to_dict(milestone)), 201


@bp.patch("/goals/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        milestone.name = name

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        if target > goal.target_amount:
            return jsonify(error="milestone target_amount cannot exceed goal target_amount"), 400
        milestone.target_amount = target

    db.session.commit()
    return jsonify(_milestone_to_dict(milestone))


@bp.delete("/goals/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = _get_or_404(goal_id, uid)
    if goal is None:
        return jsonify(error="not found"), 404

    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error="not found"), 404

    db.session.delete(milestone)
    db.session.commit()
    return jsonify(message="deleted")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_or_404(goal_id: int, user_id: int):
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    return goal


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _goal_to_dict(goal: SavingsGoal, include_milestones: bool = False) -> dict:
    progress_pct = (
        float(goal.current_amount / goal.target_amount * 100)
        if goal.target_amount > 0
        else 0.0
    )
    d = {
        "id": goal.id,
        "name": goal.name,
        "description": goal.description,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "achieved": goal.achieved,
        "progress_percent": round(progress_pct, 1),
        "remaining_amount": float(max(Decimal("0"), goal.target_amount - goal.current_amount)),
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }
    if include_milestones:
        d["milestones"] = [_milestone_to_dict(m) for m in goal.milestones]
    return d


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "name": m.name,
        "target_amount": float(m.target_amount),
        "achieved": m.achieved,
        "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
        "created_at": m.created_at.isoformat(),
    }
