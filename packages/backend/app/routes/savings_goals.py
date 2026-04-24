from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsGoal, User
from ..services.cache import cache_delete_patterns

bp = Blueprint("savings_goals", __name__)


@bp.get("")
@jwt_required()
def list_savings_goals():
    uid = int(get_jwt_identity())
    include_inactive = _as_bool(request.args.get("include_inactive"), default=False)
    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if not include_inactive:
        query = query.filter_by(active=True)
    goals = query.order_by(SavingsGoal.created_at.desc()).all()
    return jsonify([_goal_to_dict(goal) for goal in goals])


@bp.post("")
@jwt_required()
def create_savings_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    target_amount = _parse_non_negative_amount(data.get("target_amount"))
    if target_amount is None or target_amount <= 0:
        return jsonify(error="target_amount must be greater than zero"), 400

    current_amount = _parse_non_negative_amount(data.get("current_amount", 0))
    if current_amount is None:
        return jsonify(error="current_amount must be non-negative"), 400

    target_date = _parse_optional_date(data.get("target_date"))
    if target_date is False:
        return jsonify(error="invalid target_date"), 400

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
    _invalidate_goal_cache(uid)
    return jsonify(_goal_to_dict(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_savings_goal(goal_id: int):
    goal = _get_user_goal_or_404(goal_id)
    if goal is None:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_user_goal_or_404(goal_id)
    if goal is None:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        goal.name = name
    if "target_amount" in data:
        target_amount = _parse_non_negative_amount(data.get("target_amount"))
        if target_amount is None or target_amount <= 0:
            return jsonify(error="target_amount must be greater than zero"), 400
        goal.target_amount = target_amount
    if "current_amount" in data:
        current_amount = _parse_non_negative_amount(data.get("current_amount"))
        if current_amount is None:
            return jsonify(error="current_amount must be non-negative"), 400
        goal.current_amount = current_amount
    if "currency" in data:
        goal.currency = str(data.get("currency") or "INR")[:10]
    if "target_date" in data:
        target_date = _parse_optional_date(data.get("target_date"))
        if target_date is False:
            return jsonify(error="invalid target_date"), 400
        goal.target_date = target_date
    if "active" in data:
        goal.active = bool(data.get("active"))

    db.session.commit()
    _invalidate_goal_cache(uid)
    return jsonify(_goal_to_dict(goal))


@bp.post("/<int:goal_id>/contributions")
@jwt_required()
def add_savings_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_user_goal_or_404(goal_id)
    if goal is None:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    amount = _parse_non_negative_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="amount must be greater than zero"), 400

    goal.current_amount = Decimal(goal.current_amount or 0) + amount
    db.session.commit()
    _invalidate_goal_cache(uid)
    return jsonify(_goal_to_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def archive_savings_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = _get_user_goal_or_404(goal_id)
    if goal is None:
        return jsonify(error="not found"), 404
    goal.active = False
    db.session.commit()
    _invalidate_goal_cache(uid)
    return jsonify(message="archived")


def _get_user_goal_or_404(goal_id: int) -> SavingsGoal | None:
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return None
    return goal


def _goal_to_dict(goal: SavingsGoal) -> dict:
    target = Decimal(goal.target_amount or 0)
    current = Decimal(goal.current_amount or 0)
    progress = float((current / target) * 100) if target > 0 else 0.0
    remaining = max(Decimal("0"), target - current)
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": float(target),
        "current_amount": float(current),
        "remaining_amount": float(remaining),
        "progress_pct": round(progress, 2),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "active": goal.active,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
    }


def _parse_non_negative_amount(value) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _parse_optional_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return False


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _invalidate_goal_cache(uid: int) -> None:
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*"])
