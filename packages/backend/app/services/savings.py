from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from ..extensions import db
from ..models import SavingsGoal, SavingsGoalStatus, SavingsMilestone, SavingsContribution


def parse_amount(value) -> Decimal:
    """Parse and validate a Decimal amount from various input types."""
    if value is None:
        raise ValueError("Amount is required")
    try:
        if isinstance(value, Decimal):
            return Decimal(value)
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid amount: {value}")


def create_goal(
    user_id: int,
    name: str,
    target_amount,
    currency: str = "INR",
    deadline: Optional[date] = None,
) -> SavingsGoal:
    """Create a new savings goal with auto-milestones at 25%/50%/75%/100%."""
    if not name or not name.strip():
        raise ValueError("Name is required")
    
    target = parse_amount(target_amount)
    if target <= 0:
        raise ValueError("Target amount must be positive")
    
    goal = SavingsGoal(
        user_id=user_id,
        name=name.strip(),
        target_amount=target,
        current_amount=Decimal("0"),
        currency=currency,
        deadline=deadline,
        status=SavingsGoalStatus.ACTIVE,
    )
    db.session.add(goal)
    db.session.flush()  # Get the goal ID
    
    # Create auto-milestones at 25%, 50%, 75%, 100%
    _create_auto_milestones(goal)
    
    db.session.commit()
    return goal


def _create_auto_milestones(goal: SavingsGoal):
    """Create automatic milestones at 25%, 50%, 75%, 100% thresholds."""
    thresholds = [
        (Decimal("0.25"), "25% - Starting"),
        (Decimal("0.50"), "50% - Halfway"),
        (Decimal("0.75"), "75% - Almost There"),
        (Decimal("1.00"), "100% - Goal Reached"),
    ]
    
    for threshold, name in thresholds:
        milestone = SavingsMilestone(
            goal_id=goal.id,
            name=name,
            target_amount=goal.target_amount * threshold,
            reached_at=None,
        )
        db.session.add(milestone)


def add_contribution(
    goal_id: int,
    user_id: int,
    amount,
    notes: Optional[str] = None,
) -> SavingsContribution:
    """Add a contribution to a savings goal and check for milestone completion."""
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        raise ValueError("Goal not found")
    
    if goal.status != SavingsGoalStatus.ACTIVE:
        raise ValueError(f"Cannot add contribution to goal with status: {goal.status.value}")
    
    contribution_amount = parse_amount(amount)
    if contribution_amount <= 0:
        raise ValueError("Contribution amount must be positive")
    
    contribution = SavingsContribution(
        goal_id=goal_id,
        amount=contribution_amount,
        notes=notes,
    )
    
    # Update goal's current amount
    goal.current_amount += contribution_amount
    
    db.session.add(contribution)
    
    # Check and update milestones
    _check_milestones(goal)
    
    # Check if goal is now complete
    if goal.current_amount >= goal.target_amount:
        goal.status = SavingsGoalStatus.COMPLETED
    
    db.session.commit()
    return contribution


def _check_milestones(goal: SavingsGoal):
    """Mark milestones as reached when current_amount crosses threshold."""
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


def get_goal_progress(goal: SavingsGoal) -> dict:
    """Get progress stats for a savings goal."""
    target = goal.target_amount
    current = goal.current_amount
    
    if target <= 0:
        percent_complete = Decimal("0")
    else:
        percent_complete = (current / target) * 100
    
    remaining = max(target - current, Decimal("0"))
    
    days_remaining = None
    if goal.deadline:
        today = date.today()
        if goal.deadline > today:
            days_remaining = (goal.deadline - today).days
        elif goal.status == SavingsGoalStatus.ACTIVE:
            days_remaining = 0
    
    return {
        "percent_complete": float(percent_complete.quantize(Decimal("0.01"))),
        "remaining_amount": float(remaining),
        "days_remaining": days_remaining,
    }


def get_goal_with_progress(goal_id: int, user_id: int) -> Optional[SavingsGoal]:
    """Get a goal by ID and user ID."""
    return db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=user_id).first()


def list_goals(user_id: int, status: Optional[str] = None) -> list:
    """List all savings goals for a user, optionally filtered by status."""
    query = db.session.query(SavingsGoal).filter_by(user_id=user_id)
    
    if status:
        try:
            status_enum = SavingsGoalStatus(status)
            query = query.filter_by(status=status_enum)
        except ValueError:
            pass  # Ignore invalid status
    
    return query.order_by(SavingsGoal.created_at.desc()).all()


def update_goal(
    goal_id: int,
    user_id: int,
    name: Optional[str] = None,
    target_amount=None,
    deadline: Optional[date] = None,
    status: Optional[str] = None,
) -> SavingsGoal:
    """Update a savings goal."""
    goal = get_goal_with_progress(goal_id, user_id)
    if not goal:
        raise ValueError("Goal not found")
    
    if name is not None:
        if not name or not name.strip():
            raise ValueError("Name cannot be empty")
        goal.name = name.strip()
    
    if target_amount is not None:
        target = parse_amount(target_amount)
        if target <= 0:
            raise ValueError("Target amount must be positive")
        goal.target_amount = target
    
    if deadline is not None:
        goal.deadline = deadline
    
    if status is not None:
        try:
            goal.status = SavingsGoalStatus(status)
        except ValueError:
            raise ValueError(f"Invalid status: {status}")
    
    db.session.commit()
    return goal


def delete_goal(goal_id: int, user_id: int) -> bool:
    """Delete a savings goal (cascades to milestones and contributions)."""
    goal = get_goal_with_progress(goal_id, user_id)
    if not goal:
        raise ValueError("Goal not found")
    
    db.session.delete(goal)
    db.session.commit()
    return True


def mark_goal_completed(goal_id: int, user_id: int) -> SavingsGoal:
    """Manually mark a goal as completed."""
    goal = get_goal_with_progress(goal_id, user_id)
    if not goal:
        raise ValueError("Goal not found")
    
    goal.status = SavingsGoalStatus.COMPLETED
    db.session.commit()
    return goal


def abandon_goal(goal_id: int, user_id: int) -> SavingsGoal:
    """Abandon a savings goal."""
    goal = get_goal_with_progress(goal_id, user_id)
    if not goal:
        raise ValueError("Goal not found")
    
    goal.status = SavingsGoalStatus.ABANDONED
    db.session.commit()
    return goal


def list_contributions(goal_id: int, user_id: int) -> list:
    """List all contributions for a goal."""
    goal = get_goal_with_progress(goal_id, user_id)
    if not goal:
        raise ValueError("Goal not found")
    
    return (
        db.session.query(SavingsContribution)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsContribution.contributed_at.desc())
        .all()
    )


def list_milestones(goal_id: int, user_id: int) -> list:
    """List all milestones for a goal."""
    goal = get_goal_with_progress(goal_id, user_id)
    if not goal:
        raise ValueError("Goal not found")
    
    return (
        db.session.query(SavingsMilestone)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsMilestone.target_amount)
        .all()
    )