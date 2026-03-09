from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, User

bp = Blueprint("savings", __name__)
MILESTONE_PERCENTAGES = (25, 50, 75, 100)


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(SavingsGoal)
        .filter(SavingsGoal.user_id == uid)
        .order_by(SavingsGoal.created_at.desc(), SavingsGoal.id.desc())
        .all()
    )
    return jsonify([_serialize_goal(goal) for goal in items])


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    target_amount = _parse_decimal(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="target_amount must be greater than 0"), 400

    current_amount = _parse_decimal(data.get("current_amount"), default=Decimal("0"))
    if current_amount is None or current_amount < 0:
        return jsonify(error="current_amount must be greater than or equal to 0"), 400

    target_date = _parse_target_date(data.get("target_date"))
    if data.get("target_date") and target_date is None:
        return jsonify(error="target_date must be a valid ISO date"), 400

    user = db.session.get(User, uid)
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        current_amount=current_amount,
        currency=(data.get("currency") or (user.preferred_currency if user else "INR")),
        target_date=target_date,
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(id=goal.id), 201


@bp.post("/goals/<int:goal_id>/contributions")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    amount = _parse_decimal(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="amount must be greater than 0"), 400

    previous_progress = _progress_pct(goal.current_amount, goal.target_amount)
    goal.current_amount = (_to_decimal(goal.current_amount) + amount).quantize(
        Decimal("0.01")
    )
    goal.updated_at = datetime.utcnow()
    db.session.commit()

    payload = _serialize_goal(goal)
    payload["newly_reached_milestones"] = _newly_reached_milestones(
        previous_progress, payload["progress_pct"]
    )
    return jsonify(payload)


def _parse_decimal(value, default=None):
    if value is None:
        return default
    parsed = _to_decimal(value)
    if parsed is None:
        return None
    return parsed.quantize(Decimal("0.01"))


def _to_decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_target_date(raw_value):
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, date):
        return raw_value
    try:
        return date.fromisoformat(str(raw_value))
    except ValueError:
        return None


def _serialize_goal(goal: SavingsGoal) -> dict:
    target_amount = float(goal.target_amount or 0)
    current_amount = float(goal.current_amount or 0)
    progress_pct = _progress_pct(goal.current_amount, goal.target_amount)
    remaining_amount = round(max(target_amount - current_amount, 0), 2)
    milestones, next_milestone = _build_milestones(target_amount, current_amount)

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "progress_pct": progress_pct,
        "remaining_amount": remaining_amount,
        "status": _goal_status(goal, progress_pct),
        "monthly_target": _monthly_target(remaining_amount, goal.target_date),
        "milestones": milestones,
        "next_milestone": next_milestone,
    }


def _progress_pct(current_amount, target_amount) -> float:
    target = _to_decimal(target_amount) or Decimal("0")
    if target <= 0:
        return 0.0
    current = _to_decimal(current_amount) or Decimal("0")
    pct = (current / target) * Decimal("100")
    return round(float(min(pct, Decimal("100"))), 2)


def _build_milestones(target_amount: float, current_amount: float):
    milestones = []
    next_milestone = None
    for percentage in MILESTONE_PERCENTAGES:
        amount = round((target_amount * percentage) / 100, 2)
        reached = current_amount >= amount
        milestone = {"percentage": percentage, "amount": amount, "reached": reached}
        milestones.append(milestone)
        if not reached and next_milestone is None:
            next_milestone = {"percentage": percentage, "amount": amount}
    return milestones, next_milestone


def _goal_status(goal: SavingsGoal, progress_pct: float) -> str:
    if progress_pct >= 100:
        return "completed"

    if not goal.target_date:
        return "on-track"

    today = date.today()
    if goal.target_date <= today:
        return "behind"

    created_day = goal.created_at.date() if goal.created_at else today
    total_days = max((goal.target_date - created_day).days, 1)
    elapsed_days = min(max((today - created_day).days, 0), total_days)
    expected_pct = (elapsed_days / total_days) * 100
    if progress_pct >= expected_pct + 5:
        return "ahead"
    if progress_pct + 5 >= expected_pct:
        return "on-track"
    return "behind"


def _monthly_target(remaining_amount: float, target_date_value: date | None) -> float:
    if remaining_amount <= 0:
        return 0.0
    if not target_date_value:
        return 0.0
    days_remaining = (target_date_value - date.today()).days
    if days_remaining <= 0:
        return round(remaining_amount, 2)
    months_remaining = max(math.ceil(days_remaining / 30), 1)
    return round(remaining_amount / months_remaining, 2)


def _newly_reached_milestones(previous_progress: float, current_progress: float):
    reached = []
    for percentage in MILESTONE_PERCENTAGES:
        if previous_progress < percentage <= current_progress:
            reached.append(percentage)
    return reached
