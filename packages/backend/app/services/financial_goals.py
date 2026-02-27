"""Financial goal tracking & milestones.

Create savings goals, track progress with milestones,
and get projections on when goals will be reached.
"""

from datetime import datetime, date, timedelta
from ..extensions import db


class FinancialGoal(db.Model):
    __tablename__ = "financial_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0)
    deadline = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(100), default="savings")  # savings, debt, investment, emergency
    status = db.Column(db.String(20), default="active")  # active, completed, paused, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    milestones = db.relationship("GoalMilestone", backref="goal", cascade="all, delete-orphan", lazy=True)
    contributions = db.relationship("GoalContribution", backref="goal", cascade="all, delete-orphan", lazy=True)


class GoalMilestone(db.Model):
    __tablename__ = "goal_milestones"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("financial_goals.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_percentage = db.Column(db.Float, nullable=False)  # 0-100
    reached = db.Column(db.Boolean, default=False)
    reached_at = db.Column(db.DateTime, nullable=True)


class GoalContribution(db.Model):
    __tablename__ = "goal_contributions"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("financial_goals.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(300), default="")
    date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def create_goal(user_id: int, name: str, target_amount: float, deadline: str | None = None, category: str = "savings") -> dict:
    if target_amount <= 0:
        raise ValueError("target_amount must be positive")

    goal = FinancialGoal(
        user_id=user_id, name=name.strip(), target_amount=target_amount,
        deadline=date.fromisoformat(deadline) if deadline else None,
        category=category,
    )
    db.session.add(goal)
    db.session.flush()

    # Auto-create milestones at 25%, 50%, 75%, 100%
    for pct in [25, 50, 75, 100]:
        db.session.add(GoalMilestone(goal_id=goal.id, name=f"{pct}% reached", target_percentage=pct))

    db.session.commit()
    return _serialize_goal(goal)


def get_goals(user_id: int, status: str | None = None) -> list[dict]:
    q = FinancialGoal.query.filter_by(user_id=user_id)
    if status:
        q = q.filter_by(status=status)
    return [_serialize_goal(g) for g in q.order_by(FinancialGoal.created_at.desc()).all()]


def get_goal(user_id: int, goal_id: int) -> dict | None:
    g = FinancialGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    return _serialize_goal(g) if g else None


def update_goal(user_id: int, goal_id: int, **kwargs) -> dict | None:
    g = FinancialGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        return None
    for key in ("name", "target_amount", "category", "status"):
        if key in kwargs and kwargs[key] is not None:
            setattr(g, key, kwargs[key])
    if "deadline" in kwargs:
        g.deadline = date.fromisoformat(kwargs["deadline"]) if kwargs["deadline"] else None
    db.session.commit()
    return _serialize_goal(g)


def delete_goal(user_id: int, goal_id: int) -> bool:
    g = FinancialGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        return False
    db.session.delete(g)
    db.session.commit()
    return True


def add_contribution(user_id: int, goal_id: int, amount: float, note: str = "") -> dict:
    g = FinancialGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        raise ValueError("Goal not found")
    if amount <= 0:
        raise ValueError("Amount must be positive")

    contrib = GoalContribution(goal_id=g.id, amount=amount, note=note)
    db.session.add(contrib)
    g.current_amount = round(g.current_amount + amount, 2)

    # Check milestones
    pct = g.current_amount / g.target_amount * 100 if g.target_amount > 0 else 0
    for m in g.milestones:
        if not m.reached and pct >= m.target_percentage:
            m.reached = True
            m.reached_at = datetime.utcnow()

    # Auto-complete
    if g.current_amount >= g.target_amount:
        g.status = "completed"

    db.session.commit()
    return _serialize_goal(g)


def get_contributions(user_id: int, goal_id: int) -> list[dict]:
    g = FinancialGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        return []
    return [
        {"id": c.id, "amount": c.amount, "note": c.note, "date": c.date.isoformat()}
        for c in sorted(g.contributions, key=lambda x: x.date, reverse=True)
    ]


def goal_projection(user_id: int, goal_id: int) -> dict:
    """Project when a goal will be reached based on contribution history."""
    g = FinancialGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not g:
        raise ValueError("Goal not found")

    remaining = max(g.target_amount - g.current_amount, 0)
    pct = round(g.current_amount / g.target_amount * 100, 1) if g.target_amount > 0 else 0

    if not g.contributions:
        return {
            "goal_id": g.id,
            "progress_pct": pct,
            "remaining": remaining,
            "projected_completion": None,
            "on_track": None,
            "suggestion": "Start contributing to see projections.",
        }

    # Calculate average contribution rate
    dates = [c.date for c in g.contributions]
    total_contributed = sum(c.amount for c in g.contributions)
    span_days = max((max(dates) - min(dates)).days, 1)
    daily_rate = total_contributed / span_days

    if daily_rate <= 0 or remaining <= 0:
        days_left = 0
    else:
        days_left = remaining / daily_rate

    projected = date.today() + timedelta(days=int(days_left))
    on_track = g.deadline is None or projected <= g.deadline if remaining > 0 else True

    suggestion = None
    if g.deadline and not on_track:
        days_to_deadline = (g.deadline - date.today()).days
        if days_to_deadline > 0:
            needed_daily = remaining / days_to_deadline
            suggestion = f"Increase daily contributions to {needed_daily:.2f} to meet deadline."

    return {
        "goal_id": g.id,
        "progress_pct": pct,
        "remaining": round(remaining, 2),
        "daily_contribution_rate": round(daily_rate, 2),
        "projected_completion": projected.isoformat() if remaining > 0 else date.today().isoformat(),
        "on_track": on_track,
        "suggestion": suggestion,
    }


def _serialize_goal(g: FinancialGoal) -> dict:
    pct = round(g.current_amount / g.target_amount * 100, 1) if g.target_amount > 0 else 0
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": g.target_amount,
        "current_amount": g.current_amount,
        "progress_pct": pct,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "category": g.category,
        "status": g.status,
        "milestones": [
            {"id": m.id, "name": m.name, "target_pct": m.target_percentage, "reached": m.reached,
             "reached_at": m.reached_at.isoformat() if m.reached_at else None}
            for m in g.milestones
        ],
        "created_at": g.created_at.isoformat(),
    }
