"""Savings goal tracking service."""

from datetime import date
from decimal import Decimal

from ..extensions import db
from ..models import SavingsGoal, GoalContribution, GoalStatus


def create_goal(user_id, name, target_amount, currency="INR", deadline=None):
    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        currency=currency,
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()
    return goal


def get_goals(user_id, status=None):
    query = SavingsGoal.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(SavingsGoal.created_at.desc()).all()


def get_goal(goal_id, user_id):
    return SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()


def add_contribution(goal_id, user_id, amount, note=None):
    goal = get_goal(goal_id, user_id)
    if not goal:
        return None, "Goal not found"
    if goal.status != GoalStatus.ACTIVE.value:
        return None, "Goal is not active"

    contribution = GoalContribution(
        goal_id=goal_id,
        amount=amount,
        note=note,
    )
    db.session.add(contribution)

    # Atomic DB-side update to avoid race conditions
    from sqlalchemy import text

    db.session.execute(
        text(
            "UPDATE savings_goals SET current_amount = current_amount + :amt WHERE id = :gid"
        ),
        {"amt": float(amount), "gid": goal_id},
    )
    db.session.flush()
    db.session.refresh(goal)

    # Auto-complete if target reached
    if goal.current_amount >= goal.target_amount:
        goal.status = GoalStatus.COMPLETED.value

    db.session.commit()
    return contribution, None


def get_contributions(goal_id, user_id):
    goal = get_goal(goal_id, user_id)
    if not goal:
        return None
    return (
        GoalContribution.query.filter_by(goal_id=goal_id)
        .order_by(GoalContribution.contributed_at.desc())
        .all()
    )


def get_progress(goal_id, user_id):
    goal = get_goal(goal_id, user_id)
    if not goal:
        return None

    target = float(goal.target_amount)
    current = float(goal.current_amount)
    pct = round((current / target) * 100, 2) if target > 0 else 0

    result = {
        "goal_id": goal.id,
        "name": goal.name,
        "target": target,
        "current": current,
        "remaining": round(max(target - current, 0), 2),
        "progress_pct": pct,
        "status": goal.status,
        "on_track": True,
    }

    if goal.deadline:
        days_left = (goal.deadline - date.today()).days
        result["deadline"] = goal.deadline.isoformat()
        result["days_left"] = max(days_left, 0)

        if days_left > 0 and current < target:
            daily_needed = round((target - current) / days_left, 2)
            result["daily_savings_needed"] = daily_needed
            # Check if current savings pace is sufficient
            days_elapsed = (date.today() - goal.created_at.date()).days or 1
            expected_pct = (
                days_elapsed / max((goal.deadline - goal.created_at.date()).days, 1)
            ) * 100
            if pct < expected_pct * 0.8:  # more than 20% behind schedule
                result["on_track"] = False
        elif days_left <= 0 and current < target:
            result["on_track"] = False

    # Milestones
    milestones = []
    for pct_mark in [25, 50, 75, 100]:
        milestones.append(
            {
                "pct": pct_mark,
                "reached": pct >= pct_mark,
                "amount": round(target * pct_mark / 100, 2),
            }
        )
    result["milestones"] = milestones

    return result


def update_goal(goal_id, user_id, **kwargs):
    goal = get_goal(goal_id, user_id)
    if not goal:
        return None

    for key in ("name", "target_amount", "currency", "deadline", "status"):
        if key in kwargs and kwargs[key] is not None:
            setattr(goal, key, kwargs[key])

    db.session.commit()
    return goal


def cancel_goal(goal_id, user_id):
    goal = get_goal(goal_id, user_id)
    if not goal:
        return None
    goal.status = GoalStatus.CANCELLED.value
    db.session.commit()
    return goal
