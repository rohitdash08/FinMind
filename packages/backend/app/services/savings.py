"""Savings goal tracking with milestones (issue #133 — $250 bounty)."""
import logging
from datetime import date
from typing import Optional
from ..extensions import db

logger = logging.getLogger("finmind.savings")


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    target_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=date.today, nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)


class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    pct = db.Column(db.Integer, nullable=False)       # 25, 50, 75, 100
    reached_at = db.Column(db.Date, nullable=True)
    notified = db.Column(db.Boolean, default=False, nullable=False)


MILESTONE_PCTS = [25, 50, 75, 100]


def create_goal(user_id: int, name: str, target: float, currency: str = "INR",
                target_date: Optional[date] = None) -> SavingsGoal:
    goal = SavingsGoal(user_id=user_id, name=name, target_amount=target,
                       currency=currency, target_date=target_date)
    db.session.add(goal)
    db.session.flush()
    for pct in MILESTONE_PCTS:
        db.session.add(SavingsMilestone(goal_id=goal.id, pct=pct))
    db.session.commit()
    return goal


def add_contribution(goal_id: int, amount: float) -> dict:
    """Add funds to a goal. Returns updated goal + any newly reached milestones."""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal:
        raise ValueError(f"Goal {goal_id} not found")
    goal.current_amount = float(goal.current_amount or 0) + amount
    if goal.current_amount >= float(goal.target_amount):
        goal.completed = True

    reached = []
    progress_pct = (float(goal.current_amount) / float(goal.target_amount)) * 100
    milestones = db.session.query(SavingsMilestone).filter_by(goal_id=goal_id).all()
    for m in milestones:
        if not m.reached_at and progress_pct >= m.pct:
            m.reached_at = date.today()
            reached.append(m.pct)
    db.session.commit()
    return {"goal": _goal_dict(goal), "milestones_reached": reached}


def get_goal(goal_id: int) -> dict:
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal:
        raise ValueError(f"Goal {goal_id} not found")
    milestones = db.session.query(SavingsMilestone).filter_by(goal_id=goal_id).order_by(SavingsMilestone.pct).all()
    d = _goal_dict(goal)
    d["milestones"] = [{"pct": m.pct, "reached": m.reached_at is not None,
                        "reached_at": m.reached_at.isoformat() if m.reached_at else None} for m in milestones]
    return d


def list_goals(user_id: int) -> list:
    goals = db.session.query(SavingsGoal).filter_by(user_id=user_id).order_by(SavingsGoal.id.desc()).all()
    return [_goal_dict(g) for g in goals]


def _goal_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount or 0)
    return {
        "id": g.id, "name": g.name, "target_amount": target,
        "current_amount": current, "currency": g.currency,
        "progress_pct": round((current / target * 100), 1) if target > 0 else 0,
        "completed": g.completed,
        "target_date": g.target_date.isoformat() if g.target_date else None,
    }
