"""Savings goal tracking service with milestones.

Allows users to create savings goals with target amounts and deadlines,
track progress through automatic milestone generation, and get projected
completion dates based on savings rate.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any

from ..extensions import db

logger = logging.getLogger("finmind.savings")


class SavingsGoal(db.Model):
    """A savings goal with target amount and optional deadline."""

    __tablename__ = "savings_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contributions = db.relationship("GoalContribution", backref="goal", lazy="dynamic")
    milestones = db.relationship("GoalMilestone", backref="goal", lazy="dynamic")


class GoalContribution(db.Model):
    """A contribution toward a savings goal."""

    __tablename__ = "goal_contributions"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class GoalMilestone(db.Model):
    """A milestone within a savings goal (auto-generated or custom)."""

    __tablename__ = "goal_milestones"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_percentage = db.Column(db.Integer, nullable=False)
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)


def create_goal(
    user_id: int,
    name: str,
    target_amount: float,
    currency: str = "INR",
    description: str | None = None,
    deadline: date | None = None,
) -> dict[str, Any]:
    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=Decimal(str(target_amount)),
        currency=currency,
        description=description,
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.flush()

    # Auto-generate milestones at 25%, 50%, 75%, 100%
    for pct in [25, 50, 75, 100]:
        label = {25: "Quarter way", 50: "Halfway", 75: "Almost there", 100: "Goal reached!"}
        db.session.add(
            GoalMilestone(goal_id=goal.id, name=label[pct], target_percentage=pct)
        )

    db.session.commit()
    logger.info("Created savings goal id=%s user=%s target=%s", goal.id, user_id, target_amount)
    return _goal_to_dict(goal)


def add_contribution(goal_id: int, user_id: int, amount: float, notes: str | None = None) -> dict[str, Any]:
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        raise ValueError("Goal not found")
    if goal.status != "active":
        raise ValueError("Goal is not active")

    contribution = GoalContribution(
        goal_id=goal.id, amount=Decimal(str(amount)), notes=notes
    )
    db.session.add(contribution)
    goal.current_amount = Decimal(str(goal.current_amount)) + Decimal(str(amount))

    # Check and update milestones
    progress_pct = float(goal.current_amount / goal.target_amount * 100) if goal.target_amount else 0
    newly_reached = []
    for ms in goal.milestones.filter_by(reached=False).all():
        if progress_pct >= ms.target_percentage:
            ms.reached = True
            ms.reached_at = datetime.utcnow()
            newly_reached.append(ms.name)

    # Mark goal complete if target reached
    if goal.current_amount >= goal.target_amount:
        goal.status = "completed"

    db.session.commit()
    return {
        "contribution_id": contribution.id,
        "new_total": float(goal.current_amount),
        "progress_pct": round(progress_pct, 1),
        "milestones_reached": newly_reached,
        "goal_completed": goal.status == "completed",
    }


def get_goal(goal_id: int, user_id: int) -> dict[str, Any] | None:
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return None
    return _goal_to_dict(goal)


def list_goals(user_id: int, status: str | None = None) -> list[dict[str, Any]]:
    query = SavingsGoal.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    goals = query.order_by(SavingsGoal.created_at.desc()).all()
    return [_goal_to_dict(g) for g in goals]


def projected_completion(goal: SavingsGoal) -> date | None:
    if goal.current_amount >= goal.target_amount:
        return date.today()
    contributions = goal.contributions.order_by(GoalContribution.created_at.asc()).all()
    if len(contributions) < 2:
        return None
    first = contributions[0].created_at
    total_contributed = sum(float(c.amount) for c in contributions)
    days_elapsed = max((datetime.utcnow() - first).days, 1)
    daily_rate = total_contributed / days_elapsed
    if daily_rate <= 0:
        return None
    remaining = float(goal.target_amount) - float(goal.current_amount)
    days_needed = int(remaining / daily_rate) + 1
    return date.today() + timedelta(days=days_needed)


def _goal_to_dict(goal: SavingsGoal) -> dict[str, Any]:
    progress = float(goal.current_amount / goal.target_amount * 100) if goal.target_amount else 0
    milestones = [
        {
            "id": ms.id,
            "name": ms.name,
            "target_percentage": ms.target_percentage,
            "reached": ms.reached,
            "reached_at": ms.reached_at.isoformat() if ms.reached_at else None,
        }
        for ms in goal.milestones.order_by(GoalMilestone.target_percentage.asc()).all()
    ]
    proj = projected_completion(goal)
    return {
        "id": goal.id,
        "name": goal.name,
        "description": goal.description,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "currency": goal.currency,
        "progress_pct": round(progress, 1),
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "projected_completion": proj.isoformat() if proj else None,
        "status": goal.status,
        "milestones": milestones,
        "created_at": goal.created_at.isoformat(),
    }
