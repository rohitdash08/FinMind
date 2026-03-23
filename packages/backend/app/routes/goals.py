"""Goal-based savings tracking & milestones — issue #133."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, SavingsDeposit
import logging

bp = Blueprint("goals", __name__)
logger = logging.getLogger("finmind.goals")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _goal_to_dict(goal: SavingsGoal, include_milestones: bool = True) -> dict:
    progress_pct = 0.0
    if goal.target_amount and goal.target_amount > 0:
        progress_pct = float(goal.current_amount / goal.target_amount * 100)
        progress_pct = min(progress_pct, 100.0)

    d = {
        "id": goal.id,
        "name": goal.name,
        "description": goal.description,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "status": goal.status,
        "progress_pct": round(progress_pct, 2),
        "created_at": goal.created_at.isoformat(),
    }
    if include_milestones:
        d["milestones"] = [_milestone_to_dict(m) for m in goal.milestones]
    return d


def _milestone_to_dict(m: SavingsMilestone) -> dict:
    return {
        "id": m.id,
        "goal_id": m.goal_id,
        "label": m.label,
        "target_pct": float(m.target_pct),
        "reached": m.reached,
        "reached_at": m.reached_at.isoformat() if m.reached_at else None,
    }


def _deposit_to_dict(d: SavingsDeposit) -> dict:
    return {
        "id": d.id,
        "goal_id": d.goal_id,
        "amount": float(d.amount),
        "note": d.note,
        "deposited_at": d.deposited_at.isoformat(),
    }


def _sync_milestones(goal: SavingsGoal) -> list[SavingsMilestone]:
    """Mark any milestones that have been reached by the current progress."""
    if not goal.target_amount or goal.target_amount == 0:
        return []
    pct_reached = goal.current_amount / goal.target_amount * 100
    newly_reached = []
    for m in goal.milestones:
        if not m.reached and pct_reached >= m.target_pct:
            m.reached = True
            m.reached_at = datetime.utcnow()
            newly_reached.append(m)
    return newly_reached


def _update_goal_status(goal: SavingsGoal) -> None:
    """Auto-complete goal when target is reached; set active otherwise."""
    if goal.current_amount >= goal.target_amount:
        goal.status = "COMPLETED"
    elif goal.status == "COMPLETED":
        # Amount decreased below target — revert to active
        goal.status = "ACTIVE"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter:
        q = q.filter(SavingsGoal.status == status_filter.upper())
    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="target_amount must be a positive number"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline date"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        description=(data.get("description") or "").strip() or None,
        target_amount=target,
        current_amount=Decimal("0.00"),
        currency=str(data.get("currency") or "INR")[:10],
        deadline=deadline,
        status="ACTIVE",
    )
    db.session.add(goal)
    db.session.flush()  # get goal.id before adding milestones

    # Optionally seed default milestones (25 / 50 / 75 / 100 %)
    if data.get("auto_milestones", True):
        for pct, label in [
            (25, "25% reached"),
            (50, "Halfway there!"),
            (75, "75% reached"),
            (100, "Goal complete! 🎉"),
        ]:
            db.session.add(
                SavingsMilestone(
                    goal_id=goal.id,
                    label=label,
                    target_pct=Decimal(str(pct)),
                    reached=False,
                )
            )

    db.session.commit()
    logger.info("Created goal id=%s user=%s target=%s", goal.id, uid, target)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal))


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

    if "description" in data:
        goal.description = (data["description"] or "").strip() or None

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = target

    if "currency" in data:
        goal.currency = str(data["currency"] or "INR")[:10]

    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline date"), 400

    if "status" in data:
        status = str(data["status"]).upper()
        if status not in ("ACTIVE", "PAUSED", "COMPLETED", "CANCELLED"):
            return jsonify(error="invalid status"), 400
        goal.status = status

    _update_goal_status(goal)
    db.session.commit()
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
    return jsonify(message="deleted")


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------

@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def deposit_to_goal(goal_id: int):
    """Add funds toward a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    if goal.status in ("CANCELLED",):
        return jsonify(error="cannot deposit into a cancelled goal"), 400

    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="amount must be a positive number"), 400

    deposit = SavingsDeposit(
        goal_id=goal.id,
        amount=amount,
        note=(data.get("note") or "").strip() or None,
        deposited_at=date.today(),
    )
    db.session.add(deposit)

    goal.current_amount = goal.current_amount + amount
    newly_reached = _sync_milestones(goal)
    _update_goal_status(goal)

    db.session.commit()
    logger.info(
        "Deposit goal=%s user=%s amount=%s newly_reached=%s",
        goal.id, uid, amount, len(newly_reached),
    )
    return jsonify(
        goal=_goal_to_dict(goal),
        deposit=_deposit_to_dict(deposit),
        milestones_reached=[_milestone_to_dict(m) for m in newly_reached],
    ), 200


@bp.get("/<int:goal_id>/deposits")
@jwt_required()
def list_deposits(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    deposits = (
        db.session.query(SavingsDeposit)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsDeposit.deposited_at.desc())
        .all()
    )
    return jsonify([_deposit_to_dict(d) for d in deposits])


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def add_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify(error="label required"), 400

    try:
        target_pct = Decimal(str(data.get("target_pct", 0)))
    except (InvalidOperation, ValueError):
        return jsonify(error="invalid target_pct"), 400

    if target_pct <= 0 or target_pct > 100:
        return jsonify(error="target_pct must be between 1 and 100"), 400

    m = SavingsMilestone(
        goal_id=goal.id,
        label=label,
        target_pct=target_pct,
        reached=False,
    )
    db.session.add(m)
    db.session.flush()
    # Immediately check if already reached
    _sync_milestones(goal)
    db.session.commit()
    return jsonify(_milestone_to_dict(m)), 201


@bp.delete("/<int:goal_id>/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(goal_id: int, milestone_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    m = db.session.get(SavingsMilestone, milestone_id)
    if not m or m.goal_id != goal_id:
        return jsonify(error="not found"), 404
    db.session.delete(m)
    db.session.commit()
    return jsonify(message="deleted")
