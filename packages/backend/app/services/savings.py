"""Goal-based savings tracking service for FinMind.

Features:
- Create and manage savings goals
- Add contributions with automatic milestone checking
- Progress tracking and projections
- Dashboard overview of all goals
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from ..extensions import db
from ..models_savings import SavingsGoal, SavingsContribution, SavingsMilestone

logger = logging.getLogger("finmind.savings")


def create_goal(user_id: int, name: str, target_amount: float, **kwargs) -> SavingsGoal:
    """Create a new savings goal."""
    if target_amount <= 0:
        raise ValueError("Target amount must be positive")

    category = kwargs.get("category", "custom")
    if category not in SavingsGoal.GOAL_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")

    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        currency=kwargs.get("currency", "USD"),
        deadline=kwargs.get("deadline"),
        category=category,
        priority=kwargs.get("priority", "medium"),
        icon=kwargs.get("icon"),
        color=kwargs.get("color"),
        description=kwargs.get("description"),
    )
    db.session.add(goal)
    db.session.flush()

    # Create default milestones
    for pct in [25, 50, 75, 100]:
        milestone = SavingsMilestone(
            goal_id=goal.id,
            percentage=pct,
            celebration_message=SavingsMilestone.MILESTONE_MESSAGES.get(pct, ""),
        )
        db.session.add(milestone)

    db.session.commit()
    logger.info("Created savings goal %s (target: %.2f) for user %d", name, target_amount, user_id)
    return goal


def add_contribution(goal_id: int, user_id: int, amount: float, note: str = None) -> tuple[SavingsContribution, list[SavingsMilestone]]:
    """Add a contribution to a savings goal.

    Returns:
        Tuple of (contribution, newly_reached_milestones)
    """
    if amount <= 0:
        raise ValueError("Contribution amount must be positive")

    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        raise ValueError("Goal not found")
    if goal.is_completed:
        raise ValueError("Goal already completed")

    # Record contribution
    contribution = SavingsContribution(
        goal_id=goal_id,
        user_id=user_id,
        amount=amount,
        note=note,
    )
    db.session.add(contribution)

    # Update goal amount
    old_progress = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
    goal.current_amount += amount
    new_progress = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0

    # Check for newly reached milestones
    newly_reached = []
    for milestone in goal.milestones.all():
        if not milestone.is_reached and new_progress >= milestone.percentage:
            milestone.is_reached = True
            milestone.reached_at = datetime.now(timezone.utc)
            newly_reached.append(milestone)

    # Check if goal is completed
    if goal.current_amount >= goal.target_amount and not goal.is_completed:
        goal.is_completed = True
        goal.completed_at = datetime.now(timezone.utc)

    db.session.commit()
    logger.info("Added %.2f to goal %d (progress: %.1f%%)", amount, goal_id, new_progress)
    return contribution, newly_reached


def get_user_goals(user_id: int, include_completed: bool = False) -> list[SavingsGoal]:
    """Get all savings goals for a user."""
    query = SavingsGoal.query.filter_by(user_id=user_id)
    if not include_completed:
        query = query.filter_by(is_completed=False)
    return query.order_by(SavingsGoal.priority.desc(), SavingsGoal.deadline.asc().nulls_last()).all()


def get_goals_overview(user_id: int) -> dict:
    """Get savings goals dashboard overview."""
    goals = SavingsGoal.query.filter_by(user_id=user_id).all()

    total_saved = sum(g.current_amount for g in goals)
    total_target = sum(g.target_amount for g in goals)
    completed = sum(1 for g in goals if g.is_completed)
    in_progress = [g for g in goals if not g.is_completed]

    # Upcoming milestones
    upcoming = []
    for g in in_progress:
        progress = (g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 0
        next_pct = min((m for m in [25, 50, 75, 100] if progress < m), default=None)
        if next_pct:
            upcoming.append({
                "goal_id": g.id,
                "goal_name": g.name,
                "next_milestone": next_pct,
                "current_progress": round(progress, 1),
                "amount_to_milestone": round(g.target_amount * next_pct / 100 - g.current_amount, 2),
            })

    return {
        "total_goals": len(goals),
        "completed_goals": completed,
        "in_progress_goals": len(in_progress),
        "total_saved": round(total_saved, 2),
        "total_target": round(total_target, 2),
        "overall_progress": round((total_saved / total_target * 100) if total_target > 0 else 0, 1),
        "upcoming_milestones": sorted(upcoming, key=lambda x: x["current_progress"], reverse=True)[:5],
        "goals": [g.to_dict() for g in goals],
    }


def get_goal_contributions(goal_id: int, user_id: int, limit: int = 50) -> list[SavingsContribution]:
    """Get contribution history for a goal."""
    return SavingsContribution.query.filter_by(
        goal_id=goal_id, user_id=user_id
    ).order_by(SavingsContribution.created_at.desc()).limit(limit).all()


def withdraw_from_goal(goal_id: int, user_id: int, amount: float, note: str = None) -> SavingsContribution:
    """Withdraw from a savings goal (negative contribution)."""
    if amount <= 0:
        raise ValueError("Withdrawal amount must be positive")

    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        raise ValueError("Goal not found")

    if goal.current_amount < amount:
        raise ValueError("Insufficient saved amount")

    # Record as negative contribution
    contribution = SavingsContribution(
        goal_id=goal_id,
        user_id=user_id,
        amount=-amount,
        note=note or "Withdrawal from savings",
    )
    db.session.add(contribution)

    goal.current_amount -= amount
    if goal.is_completed and goal.current_amount < goal.target_amount:
        goal.is_completed = False
        goal.completed_at = None

    db.session.commit()
    return contribution
