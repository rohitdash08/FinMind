from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.savings_goal import SavingsGoal, SavingsMilestone
from app.schemas.savings_goal import (
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
    SavingsGoalCreate,
    SavingsGoalRead,
    SavingsGoalUpdate,
)

router = APIRouter(prefix="/savings", tags=["savings"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_goal_or_404(goal_id: int, user_id: int, db: Session) -> SavingsGoal:
    goal = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Savings goal not found")
    return goal


def _get_milestone_or_404(milestone_id: int, goal_id: int, db: Session) -> SavingsMilestone:
    milestone = (
        db.query(SavingsMilestone)
        .filter(SavingsMilestone.id == milestone_id, SavingsMilestone.goal_id == goal_id)
        .first()
    )
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    return milestone


# ---------------------------------------------------------------------------
# Savings Goals
# ---------------------------------------------------------------------------

@router.post("/goals", response_model=SavingsGoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: SavingsGoalCreate,
    user_id: int,
    db: Session = Depends(get_db),
):
    goal = SavingsGoal(**payload.model_dump(), user_id=user_id)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/goals", response_model=List[SavingsGoalRead])
def list_goals(
    user_id: int,
    db: Session = Depends(get_db),
):
    return db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).all()


@router.get("/goals/{goal_id}", response_model=SavingsGoalRead)
def get_goal(
    goal_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    return _get_goal_or_404(goal_id, user_id, db)


@router.patch("/goals/{goal_id}", response_model=SavingsGoalRead)
def update_goal(
    goal_id: int,
    payload: SavingsGoalUpdate,
    user_id: int,
    db: Session = Depends(get_db),
):
    goal = _get_goal_or_404(goal_id, user_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    goal = _get_goal_or_404(goal_id, user_id, db)
    db.delete(goal)
    db.commit()


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

@router.post(
    "/goals/{goal_id}/milestones",
    response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone(
    goal_id: int,
    payload: MilestoneCreate,
    user_id: int,
    db: Session = Depends(get_db),
):
    _get_goal_or_404(goal_id, user_id, db)
    milestone = SavingsMilestone(**payload.model_dump(), goal_id=goal_id)
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.get("/goals/{goal_id}/milestones", response_model=List[MilestoneRead])
def list_milestones(
    goal_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    _get_goal_or_404(goal_id, user_id, db)
    return db.query(SavingsMilestone).filter(SavingsMilestone.goal_id == goal_id).all()


@router.patch("/goals/{goal_id}/milestones/{milestone_id}", response_model=MilestoneRead)
def update_milestone(
    goal_id: int,
    milestone_id: int,
    payload: MilestoneUpdate,
    user_id: int,
    db: Session = Depends(get_db),
):
    _get_goal_or_404(goal_id, user_id, db)
    milestone = _get_milestone_or_404(milestone_id, goal_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(milestone, field, value)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete(
    "/goals/{goal_id}/milestones/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_milestone(
    goal_id: int,
    milestone_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    _get_goal_or_404(goal_id, user_id, db)
    milestone = _get_milestone_or_404(milestone_id, goal_id, db)
    db.delete(milestone)
    db.commit()
