"""Goal-based savings tracking with milestones.

Users can create savings goals with target amounts and deadlines,
contribute funds, and track progress through milestones.
"""

from datetime import datetime, date
from ..extensions import db
from ..models import Expense


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(14, 2), nullable=False)
    current_amount = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    milestones = db.relationship(
        "SavingsMilestone", backref="goal", lazy=True, cascade="all, delete-orphan"
    )


class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    target_pct = db.Column(db.Integer, nullable=False)  # e.g. 25, 50, 75, 100
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# --- Default milestones ---
DEFAULT_MILESTONES = [
    (25, "25% — Quarter way there!"),
    (50, "50% — Halfway!"),
    (75, "75% — Almost there!"),
    (100, "100% — Goal reached! 🎉"),
]


def create_goal(user_id: int, name: str, target_amount: float,
                currency: str = "INR", deadline: str | None = None) -> dict:
    if target_amount <= 0:
        raise ValueError("target_amount must be positive")

    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        currency=currency,
        deadline=date.fromisoformat(deadline) if deadline else None,
    )
    db.session.add(goal)
    db.session.flush()

    for pct, title in DEFAULT_MILESTONES:
        db.session.add(SavingsMilestone(goal_id=goal.id, title=title, target_pct=pct))

    db.session.commit()
    return _serialize_goal(goal)


def get_goals(user_id: int, status: str | None = None) -> list[dict]:
    q = SavingsGoal.query.filter_by(user_id=user_id)
    if status:
        q = q.filter_by(status=status)
    return [_serialize_goal(g) for g in q.order_by(SavingsGoal.created_at.desc()).all()]


def get_goal(user_id: int, goal_id: int) -> dict | None:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    return _serialize_goal(g) if g else None


def contribute(user_id: int, goal_id: int, amount: float) -> dict | None:
    """Add funds to a savings goal and check milestones."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g or g.status != "active":
        return None

    g.current_amount = float(g.current_amount) + amount
    progress_pct = float(g.current_amount) / float(g.target_amount) * 100

    newly_reached = []
    for m in g.milestones:
        if not m.reached and progress_pct >= m.target_pct:
            m.reached = True
            m.reached_at = datetime.utcnow()
            newly_reached.append(m.title)

    if progress_pct >= 100:
        g.status = "completed"

    db.session.commit()
    result = _serialize_goal(g)
    result["newly_reached_milestones"] = newly_reached
    return result


def update_goal(user_id: int, goal_id: int, **kwargs) -> dict | None:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        return None
    for key in ("name", "target_amount", "currency", "deadline", "status"):
        if key in kwargs:
            val = kwargs[key]
            if key == "deadline" and isinstance(val, str):
                val = date.fromisoformat(val)
            setattr(g, key, val)
    db.session.commit()
    return _serialize_goal(g)


def delete_goal(user_id: int, goal_id: int) -> bool:
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        return False
    db.session.delete(g)
    db.session.commit()
    return True


def _serialize_goal(g: SavingsGoal) -> dict:
    current = float(g.current_amount)
    target = float(g.target_amount)
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": target,
        "current_amount": current,
        "progress_pct": round(current / target * 100, 1) if target > 0 else 0,
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "milestones": [
            {
                "id": m.id,
                "title": m.title,
                "target_pct": m.target_pct,
                "reached": m.reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
            }
            for m in sorted(g.milestones, key=lambda x: x.target_pct)
        ],
        "created_at": g.created_at.isoformat(),
    }
