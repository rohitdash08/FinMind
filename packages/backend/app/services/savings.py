from datetime import datetime
from decimal import Decimal, InvalidOperation
from ..extensions import db
from ..models import (
    SavingsGoal,
    SavingsGoalStatus,
    SavingsMilestone,
    SavingsContribution,
)
import logging

logger = logging.getLogger("finmind.savings")


def parse_amount(raw) -> Decimal | None:
    """Parse and validate amount from various input formats."""
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def create_goal(
    user_id: int,
    name: str,
    target_amount: Decimal,
    currency: str = "INR",
    deadline=None,
) -> SavingsGoal:
    """Create a new savings goal."""
    goal = SavingsGoal(
        user_id=user_id,
        name=name.strip(),
        target_amount=target_amount,
        current_amount=Decimal("0"),
        currency=currency,
        deadline=deadline,
        status=SavingsGoalStatus.ACTIVE,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info(
        "Created savings goal id=%s user=%s name=%s target=%s",
        goal.id,
        user_id,
        goal.name,
        target_amount,
    )
    _create_auto_milestones(goal)
    return goal


def add_contribution(
    goal: SavingsGoal,
    amount: Decimal,
    notes: str | None = None,
) -> SavingsContribution:
    """Add a contribution to a savings goal and check for milestones."""
    contribution = SavingsContribution(
        goal_id=goal.id,
        amount=amount,
        notes=notes,
    )
    db.session.add(contribution)
    # Update current amount
    goal.current_amount += amount
    # Check if goal completed
    if goal.current_amount >= goal.target_amount:
        goal.status = SavingsGoalStatus.COMPLETED
    db.session.commit()
    logger.info(
        "Added contribution goal=%s amount=%s total=%s",
        goal.id,
        amount,
        goal.current_amount,
    )
    # Check milestones after commit
    _check_milestones(goal)
    return contribution


def mark_goal_completed(goal: SavingsGoal) -> SavingsGoal:
    """Manually mark a goal as completed."""
    goal.status = SavingsGoalStatus.COMPLETED
    db.session.commit()
    logger.info("Marked goal completed id=%s", goal.id)
    return goal


def abandon_goal(goal: SavingsGoal) -> SavingsGoal:
    """Mark a goal as abandoned."""
    goal.status = SavingsGoalStatus.ABANDONED
    db.session.commit()
    logger.info("Abandoned goal id=%s", goal.id)
    return goal


def get_goal_progress(goal: SavingsGoal) -> dict:
    """Calculate progress statistics for a goal."""
    percent = 0
    if goal.target_amount > 0:
        percent = float(goal.current_amount / goal.target_amount * 100)
    days_remaining = None
    if goal.deadline:
        delta = goal.deadline - datetime.now().date()
        days_remaining = max(0, delta.days)
    return {
        "target": float(goal.target_amount),
        "current": float(goal.current_amount),
        "percent": round(percent, 1),
        "remaining": float(goal.target_amount - goal.current_amount),
        "days_remaining": days_remaining,
    }


def _create_auto_milestones(goal: SavingsGoal):
    """Create automatic milestone checkpoints at 25%, 50%, 75%, 100%."""
    if goal.target_amount <= 0:
        return
    thresholds = [0.25, 0.50, 0.75, 1.0]
    milestone_names = ["25% saved", "Halfway there!", "75% saved", "Goal reached!"]
    for pct, name in zip(thresholds, milestone_names):
        target = goal.target_amount * Decimal(str(pct))
        existing = (
            db.session.query(SavingsMilestone)
            .filter_by(goal_id=goal.id, name=name)
            .first()
        )
        if not existing:
            milestone = SavingsMilestone(
                goal_id=goal.id,
                name=name,
                target_amount=target,
            )
            db.session.add(milestone)
    db.session.commit()


def _check_milestones(goal: SavingsGoal):
    """Check and mark reached milestones after a contribution."""
    milestones = (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal.id)
        .filter(SavingsMilestone.reached_at.is_(None))
        .order_by(SavingsMilestone.target_amount)
        .all()
    )
    for milestone in milestones:
        if goal.current_amount >= milestone.target_amount:
            milestone.reached_at = datetime.utcnow()
            logger.info(
                "Milestone reached goal=%s milestone=%s amount=%s",
                goal.id,
                milestone.id,
                milestone.target_amount,
            )
    if milestones:
        db.session.commit()
