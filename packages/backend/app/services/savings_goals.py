"""Service layer for savings goals and milestones."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from ..extensions import db
from ..models import SavingsGoal, SavingsGoalMilestone, SavingsGoalStatus


DEFAULT_MILESTONES = [
    {"name": "Getting Started", "target_percentage": 25},
    {"name": "Halfway There", "target_percentage": 50},
    {"name": "Almost There", "target_percentage": 75},
    {"name": "Goal Reached!", "target_percentage": 100},
]


def _goal_to_dict(goal: SavingsGoal) -> dict:
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    progress = round((current / target) * 100, 2) if target > 0 else 0.0
    days_remaining = None
    if goal.target_date:
        delta = goal.target_date - date.today()
        days_remaining = max(delta.days, 0)

    milestones = (
        goal.milestones.order_by(SavingsGoalMilestone.target_percentage).all()
    )

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "current_amount": current,
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status,
        "progress_pct": progress,
        "days_remaining": days_remaining,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
        "milestones": [
            {
                "id": m.id,
                "name": m.name,
                "target_percentage": m.target_percentage,
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in milestones
        ],
    }


def list_goals(user_id: int, status: Optional[str] = None) -> list[dict]:
    query = db.session.query(SavingsGoal).filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    goals = query.order_by(SavingsGoal.created_at.desc()).all()
    return [_goal_to_dict(g) for g in goals]


def get_goal(user_id: int, goal_id: int) -> Optional[dict]:
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    return _goal_to_dict(goal)


def create_goal(
    user_id: int,
    name: str,
    target_amount: float,
    currency: str = "INR",
    target_date: Optional[str] = None,
    custom_milestones: Optional[list[dict]] = None,
) -> dict:
    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=Decimal(str(target_amount)),
        currency=currency,
        target_date=date.fromisoformat(target_date) if target_date else None,
        status=SavingsGoalStatus.ACTIVE.value,
    )
    db.session.add(goal)
    db.session.flush()

    milestone_defs = custom_milestones if custom_milestones else DEFAULT_MILESTONES
    for m_def in milestone_defs:
        milestone = SavingsGoalMilestone(
            goal_id=goal.id,
            name=m_def["name"],
            target_percentage=m_def["target_percentage"],
        )
        db.session.add(milestone)

    db.session.commit()
    return _goal_to_dict(goal)


def update_goal(
    user_id: int,
    goal_id: int,
    name: Optional[str] = None,
    target_amount: Optional[float] = None,
    currency: Optional[str] = None,
    target_date: Optional[str] = None,
) -> Optional[dict]:
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    if goal.status != SavingsGoalStatus.ACTIVE.value:
        return None

    if name is not None:
        goal.name = name
    if target_amount is not None:
        goal.target_amount = Decimal(str(target_amount))
    if currency is not None:
        goal.currency = currency
    if target_date is not None:
        goal.target_date = date.fromisoformat(target_date) if target_date else None

    db.session.commit()
    _check_milestones(goal)
    return _goal_to_dict(goal)


def delete_goal(user_id: int, goal_id: int) -> bool:
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return False
    goal.status = SavingsGoalStatus.CANCELLED.value
    db.session.commit()
    return True


def add_contribution(
    user_id: int, goal_id: int, amount: float
) -> Optional[dict]:
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    if goal.status != SavingsGoalStatus.ACTIVE.value:
        return None

    goal.current_amount = goal.current_amount + Decimal(str(amount))
    db.session.commit()

    newly_reached = _check_milestones(goal)

    result = _goal_to_dict(goal)
    result["newly_reached_milestones"] = [
        {"id": m.id, "name": m.name, "target_percentage": m.target_percentage}
        for m in newly_reached
    ]
    return result


def withdraw(
    user_id: int, goal_id: int, amount: float
) -> Optional[dict]:
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    if goal.status != SavingsGoalStatus.ACTIVE.value:
        return None

    new_amount = goal.current_amount - Decimal(str(amount))
    if new_amount < 0:
        return None

    goal.current_amount = new_amount
    db.session.commit()
    return _goal_to_dict(goal)


def _check_milestones(goal: SavingsGoal) -> list[SavingsGoalMilestone]:
    """Check and update milestone status. Returns newly reached milestones."""
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    progress = (current / target) * 100 if target > 0 else 0

    newly_reached = []
    milestones = goal.milestones.filter_by(reached=False).all()
    for m in milestones:
        if progress >= m.target_percentage:
            m.reached = True
            m.reached_at = datetime.utcnow()
            newly_reached.append(m)

    if progress >= 100 and goal.status == SavingsGoalStatus.ACTIVE.value:
        goal.status = SavingsGoalStatus.COMPLETED.value

    db.session.commit()
    return newly_reached
