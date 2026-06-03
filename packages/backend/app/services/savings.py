from datetime import timezone
"""
Goal-based savings tracking with milestones.
"""
from datetime import datetime
from decimal import Decimal
from ..extensions import db


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Add index for faster queries
    __table_args__ = (
        db.Index('idx_user_status', 'user_id', 'status'),
    )
    
    milestones = db.relationship("SavingsMilestone", backref="goal", lazy="dynamic")
    deposits = db.relationship("SavingsDeposit", backref="goal", lazy="dynamic")

    @property
    def progress_percent(self):
        """Calculate progress percentage."""
        if not self.target_amount or self.target_amount == 0:
            return 0
        return min(100, float(self.current_amount / self.target_amount * 100))


class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"
    
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)


class SavingsDeposit(db.Model):
    __tablename__ = "savings_deposits"
    
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Add index for faster queries
    __table_args__ = (
        db.Index('idx_goal_user', 'goal_id', 'user_id'),
    )


def create_goal(user_id: int, name: str, target_amount: float, 
                currency: str = "INR", deadline=None, category: str = "") -> SavingsGoal:
    """Create a new savings goal with milestones.
    
    Args:
        user_id: User ID
        name: Goal name
        target_amount: Target amount to save
        currency: Currency code
        deadline: Optional deadline date
        category: Optional category
        
    Returns:
        Created SavingsGoal object
        
    Raises:
        ValueError: If target_amount is invalid
    """
    if target_amount <= 0:
        raise ValueError("Target amount must be positive")
    
    # Create goal with explicit fields (no kwargs injection)
    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=Decimal(str(target_amount)),
        currency=currency,
        deadline=deadline,
        category=category,
    )
    db.session.add(goal)
    db.session.flush()  # Get goal.id
    
    # Create milestones
    for pct in [25, 50, 75, 100]:
        milestone = SavingsMilestone(
            goal_id=goal.id,
            name=f"{pct}% reached",
            target_amount=Decimal(str(target_amount)) * pct / 100,
        )
        db.session.add(milestone)
    
    db.session.commit()
    return goal


def deposit(goal_id: int, user_id: int, amount: float, notes: str = "") -> dict:
    """Deposit money to a savings goal.
    
    Args:
        goal_id: Goal ID
        user_id: User ID (for verification)
        amount: Amount to deposit
        notes: Optional notes
        
    Returns:
        dict with deposit_id, balance, and progress
        
    Raises:
        ValueError: If goal not found, not owned by user, or not active
    """
    if amount <= 0:
        raise ValueError("Deposit amount must be positive")
    
    # Use SELECT FOR UPDATE to prevent race conditions
    goal = db.session.query(SavingsGoal).filter_by(id=goal_id).with_for_update().first()
    
    if not goal or goal.user_id != user_id:
        raise ValueError("Goal not found")
    if goal.status != "active":
        raise ValueError("Goal is not active")
    
    # Create deposit
    deposit = SavingsDeposit(
        goal_id=goal_id,
        user_id=user_id,
        amount=Decimal(str(amount)),
        notes=notes,
    )
    db.session.add(deposit)
    
    # Update goal amount
    goal.current_amount = goal.current_amount + Decimal(str(amount))
    
    # Check milestones
    for milestone in goal.milestones.filter_by(reached=False).all():
        if goal.current_amount >= milestone.target_amount:
            milestone.reached = True
            milestone.reached_at = datetime.now(timezone.utc)
    
    # Check if goal completed
    if goal.current_amount >= goal.target_amount:
        goal.status = "completed"
        goal.completed_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    return {
        "deposit_id": deposit.id,
        "balance": float(goal.current_amount),
        "progress": goal.progress_percent,
    }
