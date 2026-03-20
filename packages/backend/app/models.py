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


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ─── Bank Sync Models ────────────────────────────────────────────────────────
SQLAlchemy models for Bank Sync — add to FinMind's models.py

import uuid
from datetime import datetime


class BankAccount(db.Model):
    __tablename__ = "bank_accounts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=False)              # "setu", "mock", …
    account_id = db.Column(db.String(255), nullable=False)           # provider-side ID
    masked_account_number = db.Column(db.String(50))
    bank_name = db.Column(db.String(100))
    ifsc = db.Column(db.String(20))
    account_type = db.Column(db.String(30), default="SAVINGS")
    currency = db.Column(db.String(10), default="INR")
    holder_name = db.Column(db.String(100))
    consent_handle_id = db.Column(db.String(255))                    # AA handle
    consent_artefact_id = db.Column(db.String(255))                  # AA artefact/consentId
    consent_status = db.Column(db.String(20), default="PENDING")     # PENDING/ACTIVE/REVOKED
    last_synced_at = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = db.relationship("BankTransaction", backref="account", lazy="dynamic",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("user_id", "provider", "account_id", name="uq_bank_account"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "bank_name": self.bank_name,
            "masked_account_number": self.masked_account_number,
            "account_type": self.account_type,
            "currency": self.currency,
            "consent_status": self.consent_status,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


class BankTransaction(db.Model):
    __tablename__ = "bank_transactions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_account_id = db.Column(db.String(36), db.ForeignKey("bank_accounts.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id", ondelete="SET NULL"),
                           nullable=True)                            # linked expense (if imported)
    transaction_id = db.Column(db.String(255), nullable=False)       # provider-side txn ID
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR")
    transaction_type = db.Column(db.String(10), nullable=False)      # DEBIT / CREDIT
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False, index=True)
    balance = db.Column(db.Numeric(12, 2))
    category_hint = db.Column(db.String(100))
    raw = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("bank_account_id", "transaction_id", name="uq_bank_transaction"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "type": self.transaction_type,
            "description": self.description,
            "date": self.date.isoformat(),
            "balance": float(self.balance) if self.balance else None,
            "category_hint": self.category_hint,
            "expense_id": self.expense_id,
        }
