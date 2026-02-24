"""Goal-based savings tracking & milestones.

Users can create savings goals, contribute toward them, and track
progress through automatic milestone detection.
"""

from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import SavingsContribution, SavingsGoal, SavingsMilestone

bp = Blueprint("savings", __name__)

# Default milestones auto-created for each goal
DEFAULT_MILESTONES = [
    (25, "25% — Quarter way there!"),
    (50, "50% — Halfway!"),
    (75, "75% — Almost there!"),
    (100, "100% — Goal reached! 🎉"),
]


def _goal_dict(goal: SavingsGoal) -> dict:
    progress = (
        float(goal.current_amount) / float(goal.target_amount) * 100
        if float(goal.target_amount) > 0
        else 0
    )
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": str(goal.target_amount),
        "current_amount": str(goal.current_amount),
        "currency": goal.currency,
        "progress_pct": round(progress, 1),
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "completed": goal.completed,
        "completed_at": goal.completed_at.isoformat() + "Z" if goal.completed_at else None,
        "created_at": goal.created_at.isoformat() + "Z",
    }


def _check_milestones(goal: SavingsGoal) -> list[dict]:
    """Check and mark any newly reached milestones. Return list of newly reached."""
    if float(goal.target_amount) <= 0:
        return []

    progress = float(goal.current_amount) / float(goal.target_amount) * 100
    newly_reached = []

    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id, reached=False)
        .order_by(SavingsMilestone.target_pct)
        .all()
    )

    for ms in milestones:
        if progress >= ms.target_pct:
            ms.reached = True
            ms.reached_at = datetime.utcnow()
            newly_reached.append({
                "id": ms.id,
                "name": ms.name,
                "target_pct": ms.target_pct,
            })

    # Check goal completion
    if progress >= 100 and not goal.completed:
        goal.completed = True
        goal.completed_at = datetime.utcnow()

    return newly_reached


@bp.post("")
@jwt_required()
def create_goal():
    """Create a new savings goal with automatic milestone creation."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    target = data.get("target_amount")

    if not name:
        return jsonify(error="name is required"), 400
    if not target or Decimal(str(target)) <= 0:
        return jsonify(error="valid target_amount is required"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=Decimal(str(target)),
        currency=data.get("currency", "INR"),
        deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
    )
    db.session.add(goal)
    db.session.flush()

    # Auto-create default milestones
    for pct, label in DEFAULT_MILESTONES:
        ms = SavingsMilestone(goal_id=goal.id, name=label, target_pct=pct)
        db.session.add(ms)

    db.session.commit()
    return jsonify(_goal_dict(goal)), 201


@bp.get("")
@jwt_required()
def list_goals():
    """List all savings goals for the authenticated user."""
    uid = int(get_jwt_identity())
    status = request.args.get("status")  # active, completed, all

    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status == "active":
        query = query.filter_by(completed=False)
    elif status == "completed":
        query = query.filter_by(completed=True)

    goals = query.order_by(SavingsGoal.created_at.desc()).all()
    return jsonify(goals=[_goal_dict(g) for g in goals])


@bp.get("/<int:gid>")
@jwt_required()
def get_goal(gid: int):
    """Get goal details with milestones and recent contributions."""
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=gid, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=gid)
        .order_by(SavingsMilestone.target_pct)
        .all()
    )

    contributions = (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=gid)
        .order_by(SavingsContribution.contributed_at.desc())
        .limit(50)
        .all()
    )

    result = _goal_dict(goal)
    result["milestones"] = [
        {
            "id": m.id,
            "name": m.name,
            "target_pct": m.target_pct,
            "reached": m.reached,
            "reached_at": m.reached_at.isoformat() + "Z" if m.reached_at else None,
        }
        for m in milestones
    ]
    result["contributions"] = [
        {
            "id": c.id,
            "amount": str(c.amount),
            "notes": c.notes,
            "contributed_at": c.contributed_at.isoformat(),
        }
        for c in contributions
    ]
    return jsonify(result)


@bp.patch("/<int:gid>")
@jwt_required()
def update_goal(gid: int):
    """Update goal name, target, or deadline."""
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=gid, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        goal.target_amount = Decimal(str(data["target_amount"]))
    if "deadline" in data:
        goal.deadline = date.fromisoformat(data["deadline"]) if data["deadline"] else None

    # Re-check milestones after target change
    _check_milestones(goal)
    db.session.commit()
    return jsonify(_goal_dict(goal))


@bp.delete("/<int:gid>")
@jwt_required()
def delete_goal(gid: int):
    """Delete a savings goal and its milestones/contributions."""
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=gid, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    db.session.query(SavingsMilestone).filter_by(goal_id=gid).delete()
    db.session.query(SavingsContribution).filter_by(goal_id=gid).delete()
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="goal deleted")


@bp.post("/<int:gid>/contribute")
@jwt_required()
def contribute(gid: int):
    """Add a contribution (deposit or withdrawal) to a savings goal."""
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=gid, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404
    if goal.completed:
        return jsonify(error="goal already completed"), 400

    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or Decimal(str(amount)) == 0:
        return jsonify(error="valid amount is required"), 400

    contribution = SavingsContribution(
        goal_id=gid,
        amount=Decimal(str(amount)),
        notes=data.get("notes"),
        contributed_at=date.fromisoformat(data["contributed_at"]) if data.get("contributed_at") else date.today(),
    )
    db.session.add(contribution)

    goal.current_amount = goal.current_amount + Decimal(str(amount))
    newly_reached = _check_milestones(goal)
    db.session.commit()

    result = {
        "id": contribution.id,
        "amount": str(contribution.amount),
        "new_total": str(goal.current_amount),
        "progress_pct": round(float(goal.current_amount) / float(goal.target_amount) * 100, 1) if float(goal.target_amount) > 0 else 0,
        "completed": goal.completed,
    }
    if newly_reached:
        result["milestones_reached"] = newly_reached
    return jsonify(result), 201


@bp.get("/<int:gid>/milestones")
@jwt_required()
def list_milestones(gid: int):
    """List milestones for a goal."""
    uid = int(get_jwt_identity())
    goal = db.session.query(SavingsGoal).filter_by(id=gid, user_id=uid).first()
    if not goal:
        return jsonify(error="goal not found"), 404

    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=gid)
        .order_by(SavingsMilestone.target_pct)
        .all()
    )
    return jsonify(
        milestones=[
            {
                "id": m.id,
                "name": m.name,
                "target_pct": m.target_pct,
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() + "Z" if m.reached_at else None,
            }
            for m in milestones
        ]
    )
