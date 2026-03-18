from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal, SavingsContribution, User
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress = min((current / target * 100) if target > 0 else 0, 100)
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "progress": round(progress, 1),
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "color": g.color,
        "icon": g.icon,
        "completed": g.completed,
        "completed_at": g.completed_at.isoformat() if g.completed_at else None,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _contribution_to_dict(c: SavingsContribution) -> dict:
    return {
        "id": c.id,
        "goal_id": c.goal_id,
        "amount": float(c.amount),
        "notes": c.notes,
        "contributed_at": c.contributed_at.isoformat() if c.contributed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ── GET /savings/goals/summary ──────────────────────────────────────────
# Must be registered BEFORE the parameterized /goals/<id> routes
@bp.get("/goals/summary")
@jwt_required()
def goals_summary():
    uid = int(get_jwt_identity())
    goals = db.session.query(SavingsGoal).filter_by(user_id=uid).all()
    total_saved = sum(float(g.current_amount) for g in goals)
    total_target = sum(float(g.target_amount) for g in goals)
    completed_count = sum(1 for g in goals if g.completed)
    active_goals = [g for g in goals if not g.completed]
    nearest_deadline = None
    if active_goals:
        with_deadlines = [g for g in active_goals if g.deadline]
        if with_deadlines:
            nearest = min(with_deadlines, key=lambda g: g.deadline)
            nearest_deadline = {
                "goal_id": nearest.id,
                "name": nearest.name,
                "deadline": nearest.deadline.isoformat(),
            }
    logger.info("Summary user=%s goals=%s completed=%s", uid, len(goals), completed_count)
    return jsonify(
        total_saved=total_saved,
        total_target=total_target,
        goals_count=len(goals),
        completed_count=completed_count,
        active_count=len(active_goals),
        nearest_deadline=nearest_deadline,
    )


# ── GET /savings/goals ──────────────────────────────────────────────────
@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.completed.asc(), SavingsGoal.created_at.desc())
        .all()
    )
    logger.info("List goals user=%s count=%s", uid, len(goals))
    return jsonify([_goal_to_dict(g) for g in goals])


# ── POST /savings/goals ─────────────────────────────────────────────────
@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    try:
        target = Decimal(str(data["target_amount"]))
        if target <= 0:
            raise ValueError()
    except (KeyError, ValueError, InvalidOperation):
        return jsonify(error="target_amount must be a positive number"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="deadline must be YYYY-MM-DD"), 400

    color = data.get("color", "#4F46E5")
    icon = data.get("icon", "piggy-bank")
    currency = data.get("currency") or (user.preferred_currency if user else "INR")

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target,
        currency=currency,
        deadline=deadline,
        color=color,
        icon=icon,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created goal id=%s user=%s name=%s target=%s", goal.id, uid, name, target)
    return jsonify(_goal_to_dict(goal)), 201


# ── PUT /savings/goals/<id> ─────────────────────────────────────────────
@bp.route("/goals/<int:goal_id>", methods=["PUT", "PATCH"])
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
            return jsonify(error="name cannot be empty"), 400
        goal.name = name

    if "target_amount" in data:
        try:
            target = Decimal(str(data["target_amount"]))
            if target <= 0:
                raise ValueError()
            goal.target_amount = target
        except (ValueError, InvalidOperation):
            return jsonify(error="target_amount must be a positive number"), 400

    if "deadline" in data:
        if data["deadline"]:
            try:
                goal.deadline = date.fromisoformat(data["deadline"])
            except ValueError:
                return jsonify(error="deadline must be YYYY-MM-DD"), 400
        else:
            goal.deadline = None

    if "color" in data:
        goal.color = data["color"]
    if "icon" in data:
        goal.icon = data["icon"]
    if "currency" in data:
        goal.currency = data["currency"]

    # Check completion status after potential target change
    if not goal.completed and goal.current_amount >= goal.target_amount:
        goal.completed = True
        goal.completed_at = datetime.utcnow()
    elif goal.completed and goal.current_amount < goal.target_amount:
        goal.completed = False
        goal.completed_at = None

    db.session.commit()
    logger.info("Updated goal id=%s user=%s", goal_id, uid)
    return jsonify(_goal_to_dict(goal))


# ── DELETE /savings/goals/<id> ──────────────────────────────────────────
@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted goal id=%s user=%s", goal_id, uid)
    return jsonify(message="deleted")


# ── POST /savings/goals/<id>/contribute ─────────────────────────────────
@bp.post("/goals/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    try:
        amount = Decimal(str(data["amount"]))
        if amount <= 0:
            raise ValueError()
    except (KeyError, ValueError, InvalidOperation):
        return jsonify(error="amount must be a positive number"), 400

    contributed_at = date.today()
    if data.get("contributed_at"):
        try:
            contributed_at = date.fromisoformat(data["contributed_at"])
        except ValueError:
            return jsonify(error="contributed_at must be YYYY-MM-DD"), 400

    notes = (data.get("notes") or "").strip() or None

    contribution = SavingsContribution(
        goal_id=goal_id,
        amount=amount,
        notes=notes,
        contributed_at=contributed_at,
    )
    db.session.add(contribution)

    goal.current_amount = (goal.current_amount or Decimal("0")) + amount

    just_completed = False
    if not goal.completed and goal.current_amount >= goal.target_amount:
        goal.completed = True
        goal.completed_at = datetime.utcnow()
        just_completed = True

    db.session.commit()
    logger.info(
        "Contribution id=%s goal=%s user=%s amount=%s completed=%s",
        contribution.id, goal_id, uid, amount, just_completed,
    )
    return jsonify(
        contribution=_contribution_to_dict(contribution),
        goal=_goal_to_dict(goal),
        just_completed=just_completed,
    ), 201


# ── GET /savings/goals/<id>/contributions ───────────────────────────────
@bp.get("/goals/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    contributions = (
        goal.contributions.order_by(SavingsContribution.contributed_at.desc()).all()
    )
    logger.info("List contributions goal=%s user=%s count=%s", goal_id, uid, len(contributions))
    return jsonify([_contribution_to_dict(c) for c in contributions])
