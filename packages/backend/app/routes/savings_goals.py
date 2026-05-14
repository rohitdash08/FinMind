from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import AuditLog, SavingsGoal, SavingsMilestone, User

bp = Blueprint("savings_goals", __name__)


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc(), SavingsGoal.id.desc())
        .all()
    )
    milestones = _milestones_for_goals(uid, [g.id for g in goals])
    return jsonify([_goal_to_dict(g, milestones.get(g.id, [])) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    target_amount = _parse_amount(data.get("target_amount"))
    current_amount = _parse_amount(data.get("current_amount") or 0)
    if not name:
        return jsonify(error="name required"), 400
    if target_amount is None or target_amount <= 0:
        return jsonify(error="target_amount must be positive"), 400
    if current_amount is None or current_amount < 0:
        return jsonify(error="current_amount must be non-negative"), 400
    target_date = _parse_optional_date(data.get("target_date"))
    if target_date is False:
        return jsonify(error="invalid target_date"), 400

    user = db.session.get(User, uid)
    goal = SavingsGoal(
        user_id=uid,
        name=name[:160],
        target_amount=target_amount,
        current_amount=current_amount,
        currency=str(data.get("currency") or (user.preferred_currency if user else "INR"))[:10],
        target_date=target_date,
        status=_goal_status(current_amount, target_amount),
    )
    db.session.add(goal)
    db.session.flush()
    _replace_milestones(uid, goal, data.get("milestones") or [])
    db.session.add(AuditLog(user_id=uid, action=f"savings_goal_created:{goal.id}"))
    db.session.commit()
    return jsonify(_goal_to_dict(goal, _ordered_milestones(goal.id, uid))), 201


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        goal.name = name[:160]
    if "target_amount" in data:
        amount = _parse_amount(data.get("target_amount"))
        if amount is None or amount <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = amount
    if "current_amount" in data:
        amount = _parse_amount(data.get("current_amount"))
        if amount is None or amount < 0:
            return jsonify(error="current_amount must be non-negative"), 400
        goal.current_amount = amount
    if "currency" in data:
        goal.currency = str(data.get("currency") or "INR")[:10]
    if "target_date" in data:
        target_date = _parse_optional_date(data.get("target_date"))
        if target_date is False:
            return jsonify(error="invalid target_date"), 400
        goal.target_date = target_date
    goal.status = _goal_status(goal.current_amount, goal.target_amount)
    _sync_reached_milestones(goal)
    db.session.add(AuditLog(user_id=uid, action=f"savings_goal_updated:{goal.id}"))
    db.session.commit()
    return jsonify(_goal_to_dict(goal, _ordered_milestones(goal.id, uid)))


@bp.post("/<int:goal_id>/milestones")
@jwt_required()
def create_milestone(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    milestone, error = _build_milestone(uid, goal, request.get_json() or {})
    if error:
        return jsonify(error=error), 400
    db.session.add(milestone)
    _sync_reached_milestones(goal)
    db.session.commit()
    return jsonify(_milestone_to_dict(milestone)), 201


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.query(SavingsMilestone).filter_by(goal_id=goal.id, user_id=uid).delete()
    db.session.delete(goal)
    db.session.add(AuditLog(user_id=uid, action=f"savings_goal_deleted:{goal.id}"))
    db.session.commit()
    return jsonify(message="deleted")


def _replace_milestones(uid: int, goal: SavingsGoal, rows: list[dict]):
    for row in rows:
        milestone, error = _build_milestone(uid, goal, row)
        if error:
            continue
        db.session.add(milestone)
    _sync_reached_milestones(goal)


def _build_milestone(uid: int, goal: SavingsGoal, row: dict):
    name = str(row.get("name") or "").strip()
    amount = _parse_amount(row.get("amount"))
    if not name:
        return None, "milestone name required"
    if amount is None or amount <= 0:
        return None, "milestone amount must be positive"
    milestone = SavingsMilestone(
        user_id=uid,
        goal_id=goal.id,
        name=name[:160],
        amount=amount,
        reached=goal.current_amount >= amount,
        reached_at=datetime.utcnow() if goal.current_amount >= amount else None,
    )
    return milestone, None


def _sync_reached_milestones(goal: SavingsGoal):
    now = datetime.utcnow()
    milestones = _ordered_milestones(goal.id, goal.user_id)
    for milestone in milestones:
        should_be_reached = goal.current_amount >= milestone.amount
        if should_be_reached and not milestone.reached:
            milestone.reached = True
            milestone.reached_at = now
        elif not should_be_reached and milestone.reached:
            milestone.reached = False
            milestone.reached_at = None


def _milestones_for_goals(uid: int, goal_ids: list[int]) -> dict[int, list[SavingsMilestone]]:
    if not goal_ids:
        return {}
    rows = (
        db.session.query(SavingsMilestone)
        .filter(SavingsMilestone.user_id == uid, SavingsMilestone.goal_id.in_(goal_ids))
        .order_by(SavingsMilestone.amount.asc(), SavingsMilestone.id.asc())
        .all()
    )
    grouped: dict[int, list[SavingsMilestone]] = {}
    for row in rows:
        grouped.setdefault(row.goal_id, []).append(row)
    return grouped


def _ordered_milestones(goal_id: int, uid: int) -> list[SavingsMilestone]:
    return (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal_id, user_id=uid)
        .order_by(SavingsMilestone.amount.asc(), SavingsMilestone.id.asc())
        .all()
    )


def _goal_to_dict(goal: SavingsGoal, milestones: list[SavingsMilestone]) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status,
        "progress_pct": round((current / target) * 100, 2) if target else 0,
        "remaining_amount": round(max(target - current, 0), 2),
        "milestones": [_milestone_to_dict(m) for m in milestones],
    }


def _milestone_to_dict(milestone: SavingsMilestone) -> dict:
    return {
        "id": milestone.id,
        "goal_id": milestone.goal_id,
        "name": milestone.name,
        "amount": float(milestone.amount),
        "reached": milestone.reached,
        "reached_at": milestone.reached_at.isoformat() if milestone.reached_at else None,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_optional_date(raw):
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return False


def _goal_status(current_amount: Decimal, target_amount: Decimal) -> str:
    return "COMPLETED" if current_amount >= target_amount else "ACTIVE"
