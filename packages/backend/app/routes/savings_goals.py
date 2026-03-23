from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import GoalStatus, SavingsGoal, User
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")

_MAX_NAME_LENGTH = 200
_MAX_AMOUNT = Decimal("9999999999.99")  # fits NUMERIC(12,2)
_VALID_CURRENCIES = {
    "INR", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SGD",
    "HKD", "NZD", "SEK", "NOK", "DKK", "KRW", "ZAR", "BRL", "MXN", "PLN",
}


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    q = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status:
        status_upper = status.upper()
        if status_upper not in {s.value for s in GoalStatus}:
            return jsonify(error="invalid status filter"), 400
        q = q.filter(SavingsGoal.status == status_upper)
    items = q.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_to_dict(g) for g in items])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    # Validate name
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    if len(name) > _MAX_NAME_LENGTH:
        return jsonify(error=f"name must be {_MAX_NAME_LENGTH} characters or fewer"), 400

    # Validate target_amount
    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        return jsonify(error="invalid target_amount"), 400
    if target > _MAX_AMOUNT:
        return jsonify(error="target_amount exceeds maximum"), 400

    # Validate current_amount
    current = _parse_amount(data.get("current_amount") or 0) or Decimal("0")
    if current < 0:
        return jsonify(error="current_amount cannot be negative"), 400
    if current > _MAX_AMOUNT:
        return jsonify(error="current_amount exceeds maximum"), 400

    # Validate currency
    currency = _validate_currency(
        data.get("currency"),
        fallback=user.preferred_currency if user else "INR",
    )
    if currency is None:
        return jsonify(error="unsupported currency"), 400

    # Validate deadline
    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="invalid deadline"), 400

    # Determine initial status (auto-complete if already at target)
    status = GoalStatus.ACTIVE.value
    if current >= target:
        status = GoalStatus.COMPLETED.value

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target,
        current_amount=current,
        currency=currency,
        deadline=deadline,
        status=status,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s", goal.id, uid)
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
        if len(name) > _MAX_NAME_LENGTH:
            return jsonify(error=f"name must be {_MAX_NAME_LENGTH} characters or fewer"), 400
        goal.name = name

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            return jsonify(error="invalid target_amount"), 400
        if target > _MAX_AMOUNT:
            return jsonify(error="target_amount exceeds maximum"), 400
        goal.target_amount = target

    if "current_amount" in data:
        current = _parse_amount(data["current_amount"])
        if current is None or current < 0:
            return jsonify(error="invalid current_amount"), 400
        if current > _MAX_AMOUNT:
            return jsonify(error="current_amount exceeds maximum"), 400
        goal.current_amount = current

    if "currency" in data:
        currency = _validate_currency(data["currency"])
        if currency is None:
            return jsonify(error="unsupported currency"), 400
        goal.currency = currency

    if "deadline" in data:
        if data["deadline"]:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="invalid deadline"), 400
        else:
            goal.deadline = None

    if "status" in data:
        status_val = str(data["status"] or "").upper()
        if status_val not in {s.value for s in GoalStatus}:
            return jsonify(error="invalid status"), 400
        goal.status = status_val

    # Auto-complete when current >= target
    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = GoalStatus.COMPLETED.value

    db.session.commit()
    return jsonify(_goal_to_dict(goal))


@bp.post("/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status != GoalStatus.ACTIVE.value:
        return jsonify(error="goal is not active"), 400
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid amount"), 400
    if amount > _MAX_AMOUNT:
        return jsonify(error="amount exceeds maximum"), 400
    new_amount = Decimal(str(goal.current_amount)) + amount
    if new_amount > _MAX_AMOUNT:
        return jsonify(error="deposit would exceed maximum balance"), 400
    goal.current_amount = new_amount
    if goal.current_amount >= goal.target_amount:
        goal.status = GoalStatus.COMPLETED.value
    db.session.commit()
    logger.info("Deposit to goal id=%s amount=%s", goal.id, amount)
    return jsonify(_goal_to_dict(goal))


@bp.post("/<int:goal_id>/withdraw")
@jwt_required()
def withdraw(goal_id: int):
    """Withdraw funds from a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    if goal.status not in (GoalStatus.ACTIVE.value, GoalStatus.COMPLETED.value):
        return jsonify(error="cannot withdraw from cancelled goal"), 400
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid amount"), 400
    current = Decimal(str(goal.current_amount))
    if amount > current:
        return jsonify(error="insufficient balance"), 400
    goal.current_amount = current - amount
    # If was completed but now below target, revert to active
    if (
        goal.status == GoalStatus.COMPLETED.value
        and float(goal.current_amount) < float(goal.target_amount)
    ):
        goal.status = GoalStatus.ACTIVE.value
    db.session.commit()
    logger.info("Withdraw from goal id=%s amount=%s", goal.id, amount)
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
    logger.info("Deleted savings goal id=%s user=%s", goal.id, uid)
    return jsonify(message="deleted")


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress = round((current / target) * 100, 1) if target > 0 else 0
    milestones = []
    for pct in [25, 50, 75, 100]:
        milestones.append({
            "percentage": pct,
            "reached": progress >= pct,
        })
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "progress": progress,
        "milestones": milestones,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        val = Decimal(str(raw)).quantize(Decimal("0.01"))
        return val
    except (InvalidOperation, ValueError, TypeError):
        return None


def _validate_currency(raw, fallback: str | None = None) -> str | None:
    """Validate and normalize a currency code. Returns None if invalid."""
    if not raw and fallback:
        return fallback.upper()[:10]
    if not raw:
        return None
    code = str(raw).strip().upper()[:10]
    if code in _VALID_CURRENCIES:
        return code
    return None
