from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    SavingsGoal,
    GoalMilestone,
    GoalContribution,
    GoalCategory,
    GoalStatus,
    User,
)
from ..services.cache import cache_delete_patterns
import logging

bp = Blueprint("savings_goals", __name__)
logger = logging.getLogger("finmind.savings_goals")

DEFAULT_MILESTONES = [
    {"title": "Getting Started", "target_percentage": 25},
    {"title": "Halfway There", "target_percentage": 50},
    {"title": "Almost There", "target_percentage": 75},
    {"title": "Goal Reached!", "target_percentage": 100},
]


def _goal_to_dict(goal: SavingsGoal, include_details: bool = False) -> dict:
    target = float(goal.target_amount) if goal.target_amount else 0
    current = float(goal.current_amount) if goal.current_amount else 0
    progress = round((current / target * 100), 1) if target > 0 else 0

    result = {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "category": goal.category,
        "status": goal.status,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "notes": goal.notes,
        "progress_percentage": min(progress, 100),
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
    }

    if include_details:
        milestones = (
            GoalMilestone.query.filter_by(goal_id=goal.id)
            .order_by(GoalMilestone.target_percentage)
            .all()
        )
        result["milestones"] = [
            {
                "id": m.id,
                "title": m.title,
                "target_percentage": m.target_percentage,
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in milestones
        ]

        contributions = (
            GoalContribution.query.filter_by(goal_id=goal.id)
            .order_by(GoalContribution.created_at.desc())
            .limit(50)
            .all()
        )
        result["contributions"] = [
            {
                "id": c.id,
                "amount": float(c.amount),
                "contribution_type": c.contribution_type,
                "notes": c.notes,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in contributions
        ]

        # newly reached milestones (for celebration check)
        result["newly_reached_milestones"] = [
            m.title for m in milestones if m.reached
        ]

    return result


def _invalidate_cache(uid: int):
    cache_delete_patterns(
        [
            f"user:{uid}:savings_goals*",
            f"user:{uid}:dashboard_summary:*",
        ]
    )


def _check_milestones(goal: SavingsGoal) -> list[dict]:
    """Check and update milestones after a contribution. Returns newly reached milestones."""
    target = float(goal.target_amount) if goal.target_amount else 0
    current = float(goal.current_amount) if goal.current_amount else 0
    progress = (current / target * 100) if target > 0 else 0

    milestones = (
        GoalMilestone.query.filter_by(goal_id=goal.id, reached=False)
        .order_by(GoalMilestone.target_percentage)
        .all()
    )

    newly_reached = []
    for m in milestones:
        if progress >= m.target_percentage:
            m.reached = True
            m.reached_at = datetime.utcnow()
            newly_reached.append(
                {
                    "id": m.id,
                    "title": m.title,
                    "target_percentage": m.target_percentage,
                }
            )

    # Auto-complete goal when target is reached
    if current >= target and goal.status == GoalStatus.ACTIVE.value:
        goal.status = GoalStatus.COMPLETED.value

    return newly_reached


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status", "ACTIVE")

    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if status_filter and status_filter != "ALL":
        query = query.filter_by(status=status_filter)

    items = query.order_by(SavingsGoal.created_at.desc()).all()
    logger.info("List savings goals user=%s count=%s", uid, len(items))
    return jsonify([_goal_to_dict(g) for g in items])


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_goal_to_dict(goal, include_details=True))


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}

    if not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount are required"), 400

    target = Decimal(str(data["target_amount"]))
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400

    category = data.get("category", "OTHER")
    if category not in [c.value for c in GoalCategory]:
        return jsonify(error=f"invalid category: {category}"), 400

    goal = SavingsGoal(
        user_id=uid,
        name=data["name"],
        target_amount=target,
        current_amount=Decimal(str(data.get("current_amount", 0))),
        currency=data.get("currency")
        or (user.preferred_currency if user else "INR"),
        category=category,
        deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
        notes=data.get("notes"),
    )
    db.session.add(goal)
    db.session.flush()  # Get goal.id

    # Create default milestones
    custom_milestones = data.get("milestones")
    milestones_data = custom_milestones if custom_milestones else DEFAULT_MILESTONES
    for ms in milestones_data:
        milestone = GoalMilestone(
            goal_id=goal.id,
            title=ms["title"],
            target_percentage=ms["target_percentage"],
        )
        db.session.add(milestone)

    db.session.commit()
    _invalidate_cache(uid)
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, uid, goal.name)
    return jsonify(id=goal.id), 201


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        target = Decimal(str(data["target_amount"]))
        if target <= 0:
            return jsonify(error="target_amount must be positive"), 400
        goal.target_amount = target
    if "category" in data:
        if data["category"] not in [c.value for c in GoalCategory]:
            return jsonify(error=f"invalid category: {data['category']}"), 400
        goal.category = data["category"]
    if "deadline" in data:
        goal.deadline = (
            date.fromisoformat(data["deadline"]) if data["deadline"] else None
        )
    if "notes" in data:
        goal.notes = data["notes"]
    if "status" in data:
        if data["status"] not in [s.value for s in GoalStatus]:
            return jsonify(error=f"invalid status: {data['status']}"), 400
        goal.status = data["status"]

    goal.updated_at = datetime.utcnow()
    db.session.commit()
    _invalidate_cache(uid)
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
    _invalidate_cache(uid)
    logger.info("Deleted savings goal id=%s user=%s", goal.id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    if goal.status != GoalStatus.ACTIVE.value:
        return jsonify(error="goal is not active"), 400

    data = request.get_json() or {}
    if not data.get("amount"):
        return jsonify(error="amount is required"), 400

    amount = Decimal(str(data["amount"]))
    if amount <= 0:
        return jsonify(error="amount must be positive"), 400

    contrib_type = data.get("type", "DEPOSIT").upper()
    if contrib_type not in ("DEPOSIT", "WITHDRAWAL"):
        return jsonify(error="type must be DEPOSIT or WITHDRAWAL"), 400

    if contrib_type == "WITHDRAWAL":
        if amount > goal.current_amount:
            return jsonify(error="withdrawal exceeds current savings"), 400
        goal.current_amount -= amount
    else:
        goal.current_amount += amount

    contribution = GoalContribution(
        goal_id=goal.id,
        amount=amount,
        contribution_type=contrib_type,
        notes=data.get("notes"),
    )
    db.session.add(contribution)

    # Check milestones
    newly_reached = _check_milestones(goal)

    goal.updated_at = datetime.utcnow()
    db.session.commit()
    _invalidate_cache(uid)

    logger.info(
        "Contribution %s %s to goal id=%s user=%s",
        contrib_type,
        float(amount),
        goal.id,
        uid,
    )

    return jsonify(
        {
            "message": "contribution recorded",
            "current_amount": float(goal.current_amount),
            "progress_percentage": min(
                round(
                    float(goal.current_amount) / float(goal.target_amount) * 100, 1
                )
                if float(goal.target_amount) > 0
                else 0,
                100,
            ),
            "newly_reached_milestones": newly_reached,
            "status": goal.status,
        }
    )


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id: int):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error="not found"), 404

    contributions = (
        GoalContribution.query.filter_by(goal_id=goal.id)
        .order_by(GoalContribution.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": c.id,
                "amount": float(c.amount),
                "contribution_type": c.contribution_type,
                "notes": c.notes,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in contributions
        ]
    )


@bp.get("/summary")
@jwt_required()
def goals_summary():
    """Summary stats for savings goals (used by dashboard)."""
    uid = int(get_jwt_identity())
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid, status=GoalStatus.ACTIVE.value)
        .all()
    )

    total_target = sum(float(g.target_amount) for g in goals)
    total_saved = sum(float(g.current_amount) for g in goals)
    overall_progress = (
        round(total_saved / total_target * 100, 1) if total_target > 0 else 0
    )

    return jsonify(
        {
            "active_goals": len(goals),
            "total_target": total_target,
            "total_saved": total_saved,
            "overall_progress": min(overall_progress, 100),
        }
    )
