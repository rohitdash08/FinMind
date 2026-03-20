from datetime import datetime, date
from enum import Enum
from sqlalchemy import Enum as SAEnum, Index
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
    locale = db.Column(db.String(35), default="en-US", nullable=False)
    role = db.Column(db.String(20), default=Role.USER.value, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_users_created_at", "created_at"),
    )


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_categories_user_id_name", "user_id", "name", unique=True),
    )


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    expense_type = db.Column(db.String(20), default="EXPENSE", nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    spent_at = db.Column(db.Date, default=date.today, nullable=False, index=True)
    source_recurring_id = db.Column(
        db.Integer, db.ForeignKey("recurring_expenses.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        # Composite: list expenses by user filtered/sorted by date
        Index("ix_expenses_user_id_spent_at", "user_id", "spent_at"),
        # Composite: filter expenses by user + category
        Index("ix_expenses_user_id_category_id", "user_id", "category_id"),
        # Composite: dashboard aggregations by user + expense_type + date
        Index(
            "ix_expenses_user_id_type_spent_at",
            "user_id",
            "expense_type",
            "spent_at",
        ),
        # Composite: duplicate detection for recurring expense generation
        Index(
            "ix_expenses_user_id_recurring_spent_at",
            "user_id",
            "source_recurring_id",
            "spent_at",
        ),
    )


class RecurringCadence(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class RecurringExpense(db.Model):
    __tablename__ = "recurring_expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=True
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    expense_type = db.Column(db.String(20), default="EXPENSE", nullable=False)
    notes = db.Column(db.String(500), nullable=False)
    cadence = db.Column(SAEnum(RecurringCadence), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Composite: list active recurring expenses per user
        Index("ix_recurring_expenses_user_id_active", "user_id", "active"),
    )


class BillCadence(str, Enum):
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"
    YEARLY = "YEARLY"
    ONCE = "ONCE"


class Bill(db.Model):
    __tablename__ = "bills"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
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

    __table_args__ = (
        # Composite: list active bills per user sorted by due date
        Index("ix_bills_user_id_active_due", "user_id", "active", "next_due_date"),
    )


class Reminder(db.Model):
    __tablename__ = "reminders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=True)
    message = db.Column(db.String(500), nullable=False)
    send_at = db.Column(db.DateTime, nullable=False)
    sent = db.Column(db.Boolean, default=False, nullable=False)
    channel = db.Column(db.String(20), default="email", nullable=False)

    __table_args__ = (
        # Composite: find unsent reminders due for processing
        Index("ix_reminders_user_id_sent_send_at", "user_id", "sent", "send_at"),
        # Composite: dedup check when scheduling bill reminders
        Index(
            "ix_reminders_user_id_bill_id_channel_send_at",
            "user_id",
            "bill_id",
            "channel",
            "send_at",
        ),
    )


class AdImpression(db.Model):
    __tablename__ = "ad_impressions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    placement = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ad_impressions_created_at", "created_at"),
    )


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)
    interval = db.Column(db.String(20), default="monthly", nullable=False)


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    plan_id = db.Column(
        db.Integer, db.ForeignKey("subscription_plans.id"), nullable=False
    )
    active = db.Column(db.Boolean, default=False, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    action = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_logs_user_id_created_at", "user_id", "created_at"),
    )
