from datetime import datetime, date
from enum import Enum
from sqlalchemy import Enum as SAEnum
from .extensions import db


class Role(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    preferred_currency = db.Column(db.String(10), default="INR", nullable=False)
    role = db.Column(db.String(20), default=Role.USER.value, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    expense_type = db.Column(db.String(20), default="EXPENSE", nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    spent_at = db.Column(db.Date, default=date.today, nullable=False)
    source_recurring_id = db.Column(
        db.Integer, db.ForeignKey("recurring_expenses.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)


class RecurringCadence(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class RecurringExpense(db.Model):
    __tablename__ = "recurring_expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    expense_type = db.Column(db.String(20), default="EXPENSE", nullable=False)
    notes = db.Column(db.String(500), nullable=False)
    cadence = db.Column(SAEnum(RecurringCadence), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class BillCadence(str, Enum):
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"
    YEARLY = "YEARLY"
    ONCE = "ONCE"


class Bill(db.Model):
    __tablename__ = "bills"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    next_due_date = db.Column(db.Date, nullable=False)
    cadence = db.Column(SAEnum(BillCadence), nullable=False)
    autopay_enabled = db.Column(db.Boolean, default=False, nullable=False)
    channel_whatsapp = db.Column(db.Boolean, default=False, nullable=False)
    channel_email = db.Column(db.Boolean, default=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Reminder(db.Model):
    __tablename__ = "reminders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=True)
    message = db.Column(db.String(500), nullable=False)
    send_at = db.Column(db.DateTime, nullable=False)
    sent = db.Column(db.Boolean, default=False, nullable=False)
    channel = db.Column(db.String(20), default="email", nullable=False)


class AdImpression(db.Model):
    __tablename__ = "ad_impressions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    placement = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)
    interval = db.Column(db.String(20), default="monthly", nullable=False)


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan_id = db.Column(
        db.Integer, db.ForeignKey("subscription_plans.id"), nullable=False
    )
    active = db.Column(db.Boolean, default=False, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SavingsGoalCategory(str, Enum):
    EMERGENCY = "EMERGENCY"
    VACATION = "VACATION"
    EDUCATION = "EDUCATION"
    HOME = "HOME"
    CAR = "CAR"
    RETIREMENT = "RETIREMENT"
    INVESTMENT = "INVESTMENT"
    OTHER = "OTHER"


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    category = db.Column(
        SAEnum(SavingsGoalCategory), default=SavingsGoalCategory.OTHER, nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    milestones = db.relationship(
        "SavingsGoalMilestone", backref="goal", lazy=True, cascade="all, delete-orphan"
    )
    contributions = db.relationship(
        "SavingsGoalContribution",
        backref="goal",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def progress_pct(self) -> float:
        if not self.target_amount or float(self.target_amount) == 0:
            return 0.0
        return min(
            round(float(self.current_amount) / float(self.target_amount) * 100, 2),
            100.0,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target_amount": float(self.target_amount),
            "current_amount": float(self.current_amount),
            "currency": self.currency,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "category": self.category.value,
            "progress_pct": self.progress_pct,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "milestones": [m.to_dict() for m in self.milestones],
        }


class SavingsGoalMilestone(db.Model):
    __tablename__ = "savings_goal_milestones"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(
        db.Integer, db.ForeignKey("savings_goals.id"), nullable=False
    )
    percentage = db.Column(db.Integer, nullable=False)  # 25, 50, 75, 100
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "percentage": self.percentage,
            "reached": self.reached,
            "reached_at": self.reached_at.isoformat() if self.reached_at else None,
        }


class SavingsGoalContribution(db.Model):
    __tablename__ = "savings_goal_contributions"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(
        db.Integer, db.ForeignKey("savings_goals.id"), nullable=False
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "amount": float(self.amount),
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
