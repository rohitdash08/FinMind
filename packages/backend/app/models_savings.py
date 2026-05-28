"""Goal-based savings tracking models for FinMind.

Features:
- Savings goals with target amounts and deadlines
- Milestone tracking (25%, 50%, 75%, 100%)
- Contribution history
- Auto-calculation of progress and projections
"""

from datetime import datetime, timezone
from ..extensions import db


class SavingsGoal(db.Model):
    """Savings goal with milestones."""
    __tablename__ = "savings_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default="USD")
    deadline = db.Column(db.DateTime, nullable=True)
    category = db.Column(db.String(50), nullable=True)  # emergency, vacation, car, house, education, retirement, custom
    priority = db.Column(db.String(10), default="medium")  # low, medium, high
    icon = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(7), nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    contributions = db.relationship("SavingsContribution", backref="goal", lazy="dynamic", order_by="SavingsContribution.created_at.desc()")
    milestones = db.relationship("SavingsMilestone", backref="goal", lazy="dynamic", order_by="SavingsMilestone.percentage")

    GOAL_CATEGORIES = ["emergency", "vacation", "car", "house", "education", "retirement", "healthcare", "wedding", "custom"]

    def to_dict(self):
        progress = (self.current_amount / self.target_amount * 100) if self.target_amount > 0 else 0
        remaining = max(0, self.target_amount - self.current_amount)

        # Calculate projection
        days_left = None
        monthly_needed = None
        if self.deadline and not self.is_completed:
            delta = (self.deadline - datetime.now(timezone.utc)).days
            if delta > 0:
                days_left = delta
                monthly_needed = remaining / (delta / 30.0) if delta > 0 else None

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target_amount": self.target_amount,
            "current_amount": self.current_amount,
            "currency": self.currency,
            "category": self.category,
            "priority": self.priority,
            "icon": self.icon,
            "color": self.color,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress_percentage": round(min(progress, 100), 2),
            "remaining_amount": round(remaining, 2),
            "days_left": days_left,
            "monthly_contribution_needed": round(monthly_needed, 2) if monthly_needed else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SavingsContribution(db.Model):
    """Individual contribution to a savings goal."""
    __tablename__ = "savings_contributions"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(500), nullable=True)
    contribution_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "amount": self.amount,
            "note": self.note,
            "contribution_date": self.contribution_date.isoformat() if self.contribution_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SavingsMilestone(db.Model):
    """Milestone for a savings goal."""
    __tablename__ = "savings_milestones"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False, index=True)
    percentage = db.Column(db.Integer, nullable=False)  # 25, 50, 75, 100
    is_reached = db.Column(db.Boolean, default=False)
    reached_at = db.Column(db.DateTime, nullable=True)
    celebration_message = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    MILESTONE_MESSAGES = {
        25: "Great start! You are a quarter of the way there! \U0001f31f",
        50: "Halfway there! Keep up the amazing progress! \U0001f4aa",
        75: "Almost there! The finish line is in sight! \U0001f3c1",
        100: "Goal achieved! You did it! \U0001f389\U0001f388",
    }

    def to_dict(self):
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "percentage": self.percentage,
            "is_reached": self.is_reached,
            "reached_at": self.reached_at.isoformat() if self.reached_at else None,
            "celebration_message": self.celebration_message,
        }
