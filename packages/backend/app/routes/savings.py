"""Goal-based savings tracking & milestones (Issue #133).

Provides CRUD for savings goals, contribution tracking, milestone detection,
and progress analytics.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, SavingsContribution, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")

# Milestone thresholds (percentage of target)
MILESTONES = [25, 50, 75, 100]


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _goal_to_dict(goal: SavingsGoal, include_contributions: bool = False) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    pct = round((current / target) * 100, 1) if target > 0 else 0.0
    remaining = max(0.0, round(target - current, 2))

    data = {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "progress_pct": pct,
        "remaining": remaining,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "category": goal.category,
        "status": goal.status,
        "milestones_reached": _milestones_reached(pct),
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }

    if include_contributions:
        contribs = (
            goal.contributions
            .order_by(SavingsContribution.contributed_at.desc())
            .all()
        )
        data["contributions"] = [
            {
                "id": c.id,
                "amount": float(c.amount),
                "note": c.note,
                "contributed_at": c.contributed_at.isoformat(),
            }
            for c in contribs
        ]

    return data


def _milestones_reached(pct: float) -> list[int]:
    """Return list of milestone thresholds that have been reached."""
    return [m for m in MILESTONES if pct >= m]


def _check_and_update_status(goal: SavingsGoal):
    """Auto-complete goal if 100% reached."""
    if goal.target_amount > 0 and goal.current_amount >= goal.target_amount:
        if goal.status == SavingsGoalStatus.ACTIVE.value:
            goal.status = SavingsGoalStatus.COMPLETED.value


# ─── Routes ────────────────────────────────────────────────────────────────


@bp.get("/goals")
@jwt_required()
def list_goals():
    """List all savings goals for the current user.

    Query params:
        status: Filter by status (ACTIVE, COMPLETED, PAUSED)
    """
    uid = int(get_jwt_identity())
    q = SavingsGoal.query.filter_by(user_id=uid)

    status_filter = request.args.get("status")
    if status_filter and status_filter.upper() in {s.value for s in SavingsGoalStatus}:
        q = q.filter_by(status=status_filter.upper())

    goals = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_to_dict(g) for g in goals])


@bp.post("/goals")
@jwt_required()
def create_goal():
    """Create a new savings goal."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

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
        target_amount=target,
        currency=data.get("currency") or (user.preferred_currency if user else "INR"),
        deadline=deadline,
        category=(data.get("category") or "").strip() or None,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s target=%s", goal.id, uid, target)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    """Get a single savings goal with its contributions."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal, include_contributions=True))


@bp.patch("/goals/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    """Update a savings goal."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        goal.name = name

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = target

    if "deadline" in data:
        if data["deadline"] is None:
            goal.deadline = None
        else:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline"), 400

    if "category" in data:
        goal.category = (data["category"] or "").strip() or None

    if "status" in data:
        status = (data["status"] or "").upper().strip()
        if status not in {s.value for s in SavingsGoalStatus}:
            return jsonify(error="invalid status"), 400
        goal.status = status

    _check_and_update_status(goal)
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    """Delete a savings goal and all its contributions."""
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/goals/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    """Add a contribution to a savings goal.

    Body: {"amount": 100.00, "note": "monthly savings"}
    """
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="amount must be a positive number"), 400

    contributed_at = date.today()
    if data.get("contributed_at"):
        try:
            contributed_at = date.fromisoformat(data["contributed_at"])
        except ValueError:
            return jsonify(error="invalid contributed_at date"), 400

    contribution = SavingsContribution(
        goal_id=goal.id,
        amount=amount,
        note=(data.get("note") or "").strip() or None,
        contributed_at=contributed_at,
    )
    db.session.add(contribution)

    goal.current_amount = Decimal(str(goal.current_amount)) + amount
    _check_and_update_status(goal)
    goal.updated_at = datetime.utcnow()
    db.session.commit()

    logger.info(
        "Contribution id=%s goal=%s amount=%s new_total=%s",
        contribution.id,
        goal.id,
        amount,
        goal.current_amount,
    )
    return jsonify(_goal_to_dict(goal, include_contributions=True)), 201


@bp.get("/goals/<int:goal_id>/milestones")
@jwt_required()
def milestones(goal_id: int):
    """Get milestone status for a savings goal.

    Returns which milestones (25%, 50%, 75%, 100%) have been reached
    and which is the next upcoming one.
    """
    uid = int(get_jwt_identity())
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=uid).first()
    if not goal:
        return jsonify(error="not found"), 404

    target = float(goal.target_amount)
    current = float(goal.current_amount)
    pct = round((current / target) * 100, 1) if target > 0 else 0.0

    reached = _milestones_reached(pct)
    upcoming = [m for m in MILESTONES if m not in reached]
    next_milestone = upcoming[0] if upcoming else None
    amount_to_next = (
        round((next_milestone / 100) * target - current, 2)
        if next_milestone
        else 0.0
    )

    return jsonify(
        goal_id=goal.id,
        progress_pct=pct,
        milestones=[
            {
                "threshold": m,
                "reached": m in reached,
                "amount_at_threshold": round((m / 100) * target, 2),
            }
            for m in MILESTONES
        ],
        next_milestone=next_milestone,
        amount_to_next=amount_to_next,
    )
