"""Savings goals service.

Track savings goals with target amounts, deadlines, and milestone progress.
"""

from datetime import date, datetime

from sqlalchemy import func

from ..extensions import db
from ..models import Expense


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    achieved = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    milestones = db.relationship("GoalMilestone", backref="goal", lazy=True,
                                  order_by="GoalMilestone.threshold_pct")


class GoalMilestone(db.Model):
    __tablename__ = "goal_milestones"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    threshold_pct = db.Column(db.Integer, nullable=False)  # e.g. 25, 50, 75, 100
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)


def _goal_to_dict(g: SavingsGoal) -> dict:
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress = round((current / target * 100), 2) if target > 0 else 0
    days_left = (g.deadline - date.today()).days if g.deadline else None
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "currency": g.currency,
        "progress_pct": progress,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "days_left": days_left,
        "achieved": g.achieved,
        "milestones": [
            {
                "id": m.id,
                "name": m.name,
                "threshold_pct": m.threshold_pct,
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in g.milestones
        ],
    }


def _check_milestones(goal: SavingsGoal):
    """Update milestone status based on current progress."""
    target = float(goal.target_amount)
    current = float(goal.current_amount)
    if target <= 0:
        return
    progress = current / target * 100
    for m in goal.milestones:
        if not m.reached and progress >= m.threshold_pct:
            m.reached = True
            m.reached_at = datetime.utcnow()
    if current >= target and not goal.achieved:
        goal.achieved = True


DEFAULT_MILESTONES = [
    (25, "25% — Quarter way there!"),
    (50, "50% — Halfway!"),
    (75, "75% — Almost there!"),
    (100, "100% — Goal achieved!"),
]


def create_goal(user_id: int, name: str, target_amount: float,
                currency: str = "INR", deadline: str | None = None) -> dict:
    dl = date.fromisoformat(deadline) if deadline else None
    g = SavingsGoal(
        user_id=user_id, name=name, target_amount=target_amount,
        currency=currency, deadline=dl,
    )
    db.session.add(g)
    db.session.flush()
    for pct, label in DEFAULT_MILESTONES:
        m = GoalMilestone(goal_id=g.id, name=label, threshold_pct=pct)
        db.session.add(m)
    db.session.commit()
    return _goal_to_dict(g)


def list_goals(user_id: int) -> list[dict]:
    goals = SavingsGoal.query.filter_by(user_id=user_id).order_by(
        SavingsGoal.created_at.desc()
    ).all()
    return [_goal_to_dict(g) for g in goals]


def get_goal(user_id: int, goal_id: int) -> dict | None:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    return _goal_to_dict(g) if g else None


def contribute(user_id: int, goal_id: int, amount: float) -> dict:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        raise ValueError("Goal not found.")
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    g.current_amount = float(g.current_amount) + amount
    _check_milestones(g)
    db.session.commit()
    return _goal_to_dict(g)


def update_goal(user_id: int, goal_id: int, **kwargs) -> dict:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        raise ValueError("Goal not found.")
    if "name" in kwargs and kwargs["name"]:
        g.name = kwargs["name"]
    if "target_amount" in kwargs and kwargs["target_amount"]:
        g.target_amount = kwargs["target_amount"]
    if "deadline" in kwargs:
        g.deadline = date.fromisoformat(kwargs["deadline"]) if kwargs["deadline"] else None
    _check_milestones(g)
    db.session.commit()
    return _goal_to_dict(g)


def delete_goal(user_id: int, goal_id: int) -> bool:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        return False
    GoalMilestone.query.filter_by(goal_id=g.id).delete()
    db.session.delete(g)
    db.session.commit()
    return True
