# Savings Goal models for goal-based tracking
from datetime import datetime, date
from .extensions import db


class SavingsGoal(db.Model):
    """User's savings goal with milestones tracking."""
    __tablename__ = "savings_goals"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    icon = db.Column(db.String(50), nullable=True)  # Emoji or icon name
    color = db.Column(db.String(7), nullable=True)  # Hex color code
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", backref="savings_goals")
    milestones = db.relationship("SavingsMilestone", back_populates="goal", cascade="all, delete-orphan")
    
    @property
    def progress_percentage(self):
        """Calculate progress percentage."""
        if self.target_amount == 0:
            return 0
        return min(100, round((float(self.current_amount) / float(self.target_amount)) * 100, 2))
    
    @property
    def remaining_amount(self):
        """Calculate remaining amount to reach goal."""
        return max(0, float(self.target_amount) - float(self.current_amount))


class SavingsMilestone(db.Model):
    """Milestones within a savings goal."""
    __tablename__ = "savings_milestones"
    
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    is_reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    goal = db.relationship("SavingsGoal", back_populates="milestones")
    
    @property
    def progress_percentage(self):
        """Calculate milestone progress percentage."""
        if self.target_amount == 0:
            return 0
        return min(100, round((float(self.goal.current_amount) / float(self.target_amount)) * 100, 2))
