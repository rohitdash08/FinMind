from datetime import datetime, date, timedelta
from enum import Enum
from sqlalchemy import Enum as SAEnum, Index, desc, func
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


class JobStatus(str, Enum):
    """Lifecycle states for a background job."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD = "DEAD"


class JobType(str, Enum):
    """Known job categories."""
    REMINDER = "REMINDER"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    IMPORT = "IMPORT"
    INSIGHT = "INSIGHT"
    CUSTOM = "CUSTOM"


class JobExecution(db.Model):
    """Tracks background job execution, retries, and outcomes."""
    __tablename__ = "job_executions"

    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(SAEnum(JobType), nullable=False, default=JobType.CUSTOM)
    status = db.Column(SAEnum(JobStatus), nullable=False, default=JobStatus.PENDING)
    payload = db.Column(db.Text, nullable=True)
    result = db.Column(db.Text, nullable=True)

    # Retry tracking
    attempt = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    next_retry_at = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Dead-letter metadata
    dead_reason = db.Column(db.Text, nullable=True)
    dead_at = db.Column(db.DateTime, nullable=True)

    # Foreign key link
    source_id = db.Column(db.Integer, nullable=True)
    source_type = db.Column(db.String(50), nullable=True)

    __table_args__ = (
        Index("ix_job_exec_status", "status"),
        Index("ix_job_exec_type_status", "job_type", "status"),
        Index("ix_job_exec_retry_at", "status", "next_retry_at"),
        Index("ix_job_exec_created_at", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_type": self.job_type.value if self.job_type else None,
            "status": self.status.value if self.status else None,
            "payload": self.payload,
            "result": self.result,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "dead_reason": self.dead_reason,
            "dead_at": self.dead_at.isoformat() if self.dead_at else None,
            "source_id": self.source_id,
            "source_type": self.source_type,
        }


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


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
