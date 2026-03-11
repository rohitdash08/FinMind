from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Enum, Text
from sqlalchemy.orm import relationship

from app.database import Base


class GoalStatus(str, PyEnum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    target_amount = Column(Numeric(12, 2), nullable=False)
    current_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(Enum(GoalStatus), nullable=False, default=GoalStatus.active)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    milestones = relationship("SavingsMilestone", back_populates="goal", cascade="all, delete-orphan")


class SavingsMilestone(Base):
    __tablename__ = "savings_milestones"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("savings_goals.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    reached_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    goal = relationship("SavingsGoal", back_populates="milestones")
