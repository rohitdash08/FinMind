from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.savings_goal import GoalStatus


# --- Milestone schemas ---

class MilestoneBase(BaseModel):
    name: str = Field(..., max_length=255)
    target_amount: Decimal = Field(..., gt=0)


class MilestoneCreate(MilestoneBase):
    pass


class MilestoneUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    target_amount: Optional[Decimal] = Field(None, gt=0)
    reached_at: Optional[datetime] = None


class MilestoneRead(MilestoneBase):
    id: int
    goal_id: int
    reached_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# --- SavingsGoal schemas ---

class SavingsGoalBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    target_amount: Decimal = Field(..., gt=0)
    currency: str = Field("USD", max_length=3)
    deadline: Optional[datetime] = None


class SavingsGoalCreate(SavingsGoalBase):
    pass


class SavingsGoalUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    target_amount: Optional[Decimal] = Field(None, gt=0)
    current_amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    status: Optional[GoalStatus] = None
    deadline: Optional[datetime] = None


class SavingsGoalRead(SavingsGoalBase):
    id: int
    user_id: int
    current_amount: Decimal
    status: GoalStatus
    created_at: datetime
    updated_at: datetime
    milestones: List[MilestoneRead] = []

    class Config:
        from_attributes = True
