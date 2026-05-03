from datetime import datetime, date
from enum import Enum

from .extensions import db


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(
        db.String(20), default=GoalStatus.ACTIVE.value, nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    milestones = db.relationship(
        "SavingsMilestone",
        backref="goal",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    contributions = db.relationship(
        "SavingsContribution",
        backref="goal",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(
        db.Integer, db.ForeignKey("savings_goals.id"), nullable=False
    )
    percentage = db.Column(db.Integer, nullable=False)
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SavingsContribution(db.Model):
    __tablename__ = "savings_contributions"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(
        db.Integer, db.ForeignKey("savings_goals.id"), nullable=False
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    contributed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
