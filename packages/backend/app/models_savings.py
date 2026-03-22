from datetime import datetime
from .extensions import db


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    icon = db.Column(db.String(10), default="🎯")
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency = db.Column(db.String(10), nullable=False, default="INR")
    deadline = db.Column(db.Date, nullable=True)
    deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    milestones = db.relationship(
        "SavingsMilestone", backref="goal", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def progress_pct(self) -> float:
        if not self.target_amount:
            return 0.0
        return round(float(self.current_amount) / float(self.target_amount) * 100, 1)

    @property
    def is_completed(self) -> bool:
        return float(self.current_amount) >= float(self.target_amount)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "target_amount": float(self.target_amount),
            "current_amount": float(self.current_amount),
            "currency": self.currency,
            "progress_pct": self.progress_pct,
            "is_completed": self.is_completed,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "milestones": [
                m.to_dict() for m in sorted(self.milestones, key=lambda m: m.percentage)
            ],
        }


class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(
        db.Integer, db.ForeignKey("savings_goals.id"), nullable=False, index=True
    )
    percentage = db.Column(db.Integer, nullable=False)  # 25 | 50 | 75 | 100
    threshold_amount = db.Column(db.Numeric(12, 2), nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "percentage": self.percentage,
            "threshold_amount": float(self.threshold_amount),
            "reached": self.reached_at is not None,
            "reached_at": self.reached_at.isoformat() if self.reached_at else None,
        }
