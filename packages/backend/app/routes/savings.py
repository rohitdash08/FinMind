"""Goal-based savings tracking: goals, deposits, and milestone badges."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import ceil

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, SavingsDeposit, GoalStatus, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")

# Milestone thresholds (percent)
MILESTONES = [25, 50, 75, 100]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_amount(raw) -> Decimal | None:
    try:
        v = Decimal(str(raw)).quantize(Decimal("0.01"))
        if v < Decimal("0.01"):
            return None
        return v
    except (InvalidOperation, ValueError, TypeError):
        return None


def _milestones_reached(pct: float) -> list[int]:
    return [m for m in MILESTONES if pct >= m]


def _estimated_completion(goal: "SavingsGoal") -> str | None:
    """Return ISO date estimate based on deposit velocity (last 30 days)."""
    remaining = float(goal.target_amount) - float(goal.current_amount)
    if remaining <= 0:
        return None
    cutoff = datetime.utcnow().date()
    recent = [
        d
        for d in goal.deposits
        if d.deposited_at >= cutoff.replace(day=max(1, cutoff.day - 30))
    ]
    if not recent:
        return None
    total_recent = sum(float(d.amount) for d in recent)
    days_span = max(1, (cutoff - min(d.deposited_at for d in recent)).days + 1)
    daily_rate = total_recent / days_span
    if daily_rate <= 0:
        return None
    days_needed = ceil(remaining / daily_rate)
    from datetime import timedelta

    est = cutoff + timedelta(days=days_needed)
    return est.isoformat()


def _goal_to_dict(g: "SavingsGoal", include_deposits: bool = False) -> dict:
    pct = (
        (float(g.current_amount) / float(g.target_amount) * 100)
        if float(g.target_amount) > 0
        else 0.0
    )
    milestones = _milestones_reached(pct)
    result = {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "currency": g.currency,
        "status": g.status.value,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "color": g.color,
        "icon": g.icon,
        "progress_pct": round(pct, 2),
        "milestones_reached": milestones,
        "estimated_completion": _estimated_completion(g),
        "created_at": g.created_at.isoformat(),
    }
    if include_deposits:
        result["deposits"] = [
            _deposit_to_dict(d)
            for d in sorted(g.deposits, key=lambda d: d.deposited_at, reverse=True)
        ]
    return result


def _deposit_to_dict(d: "SavingsDeposit") -> dict:
    return {
        "id": d.id,
        "goal_id": d.goal_id,
        "amount": float(d.amount),
        "note": d.note,
        "deposited_at": d.deposited_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Goals — CRUD
# ---------------------------------------------------------------------------


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.status, SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    target = _parse_amount(data.get("target_amount"))
    if target is None:
        return jsonify(error="target_amount must be a positive number"), 400

    currency = data.get("currency") or (user.preferred_currency if user else "INR")

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline date"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target,
        current_amount=Decimal("0.00"),
        currency=currency,
        status=GoalStatus.ACTIVE,
        deadline=deadline,
        color=data.get("color") or "#6366f1",
        icon=data.get("icon") or "piggy-bank",
    )
    db.session.add(goal)
    db.session.commit()
    logger.info(
        "Created savings goal id=%s user=%s name=%s target=%s",
        goal.id,
        uid,
        goal.name,
        goal.target_amount,
    )
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal, include_deposits=True))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        goal.name = name

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None:
            return jsonify(error="target_amount must be a positive number"), 400
        goal.target_amount = target
        # Re-check completion after target change
        if (
            float(goal.current_amount) >= float(goal.target_amount)
            and goal.status == GoalStatus.ACTIVE
        ):
            goal.status = GoalStatus.COMPLETED

    if "currency" in data:
        goal.currency = str(data["currency"])[:10]

    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline date"), 400

    if "status" in data:
        try:
            goal.status = GoalStatus(data["status"])
        except ValueError:
            return jsonify(error="invalid status"), 400

    if "color" in data:
        goal.color = data.get("color") or goal.color

    if "icon" in data:
        goal.icon = data.get("icon") or goal.icon

    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------


@bp.post("/<int:goal_id>/deposits")
@jwt_required()
def add_deposit(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status == GoalStatus.COMPLETED:
        return jsonify(error="goal already completed"), 400
    if goal.status == GoalStatus.PAUSED:
        return jsonify(error="goal is paused — resume it before adding deposits"), 400

    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="amount must be a positive number"), 400

    note = (data.get("note") or "").strip() or None
    dep_date_raw = data.get("deposited_at")
    dep_date = date.today()
    if dep_date_raw:
        try:
            dep_date = date.fromisoformat(dep_date_raw)
        except ValueError:
            return jsonify(error="invalid deposited_at date"), 400

    deposit = SavingsDeposit(
        goal_id=goal.id,
        amount=amount,
        note=note,
        deposited_at=dep_date,
    )
    db.session.add(deposit)

    prev_pct = (
        float(goal.current_amount) / float(goal.target_amount) * 100
        if float(goal.target_amount) > 0
        else 0
    )
    goal.current_amount = (Decimal(str(goal.current_amount)) + amount).quantize(
        Decimal("0.01")
    )
    new_pct = (
        float(goal.current_amount) / float(goal.target_amount) * 100
        if float(goal.target_amount) > 0
        else 0
    )

    newly_reached = [m for m in MILESTONES if prev_pct < m <= new_pct]

    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = GoalStatus.COMPLETED
        logger.info("Savings goal id=%s auto-completed user=%s", goal.id, uid)

    db.session.commit()
    logger.info(
        "Deposit goal_id=%s user=%s amount=%s new_total=%s",
        goal.id,
        uid,
        amount,
        goal.current_amount,
    )

    return (
        jsonify(
            {
                "deposit": _deposit_to_dict(deposit),
                "goal": _goal_to_dict(goal),
                "milestones_newly_reached": newly_reached,
            }
        ),
        201,
    )


@bp.get("/<int:goal_id>/deposits")
@jwt_required()
def list_deposits(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    deposits = sorted(goal.deposits, key=lambda d: d.deposited_at, reverse=True)
    return jsonify([_deposit_to_dict(d) for d in deposits])


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@bp.get("/summary")
@jwt_required()
def summary():
    uid = int(get_jwt_identity())
    goals = db.session.query(SavingsGoal).filter_by(user_id=uid).all()
    total_target = sum(float(g.target_amount) for g in goals)
    total_saved = sum(float(g.current_amount) for g in goals)
    active = [g for g in goals if g.status == GoalStatus.ACTIVE]
    completed = [g for g in goals if g.status == GoalStatus.COMPLETED]
    nearest_deadline = None
    future = [g for g in active if g.deadline and g.deadline >= date.today()]
    if future:
        nearest_deadline = min(future, key=lambda g: g.deadline).deadline.isoformat()
    return jsonify(
        {
            "total_goals": len(goals),
            "active_goals": len(active),
            "completed_goals": len(completed),
            "total_target": round(total_target, 2),
            "total_saved": round(total_saved, 2),
            "total_remaining": round(max(0.0, total_target - total_saved), 2),
            "overall_progress_pct": (
                round(total_saved / total_target * 100, 2) if total_target > 0 else 0.0
            ),
            "nearest_deadline": nearest_deadline,
        }
    )
