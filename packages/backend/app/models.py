from datetime import datetime, date
from enum import Enum as PyEnum

from .extensions import db


class CadenceEnum(PyEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class AccountTypeEnum(PyEnum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CREDIT_CARD = "CREDIT_CARD"
    INVESTMENT = "INVESTMENT"
    LOAN = "LOAN"
    CASH = "CASH"
    OTHER = "OTHER"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    categories = db.relationship("Category", back_populates="user", lazy="dynamic")
    expenses = db.relationship("Expense", back_populates="user", lazy="dynamic")
    bills = db.relationship("Bill", back_populates="user", lazy="dynamic")
    reminders = db.relationship("Reminder", back_populates="user", lazy="dynamic")
    accounts = db.relationship("Account", back_populates="user", lazy="dynamic")


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    account_type = db.Column(db.Enum(AccountTypeEnum), nullable=False, default=AccountTypeEnum.CHECKING)
    currency = db.Column(db.String(10), nullable=False, default="USD")
    balance = db.Column(db.Numeric(14, 2), nullable=False, default=0.0)
    institution = db.Column(db.String(255))
    notes = db.Column(db.Text)
    color = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="accounts")
    expenses = db.relationship("Expense", back_populates="account", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "account_type": self.account_type.value,
            "currency": self.currency,
            "balance": float(self.balance),
            "institution": self.institution,
            "notes": self.notes,
            "color": self.color,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20))
    icon = db.Column(db.String(50))
    budget_limit = db.Column(db.Numeric(14, 2))

    user = db.relationship("User", back_populates="categories")
    expenses = db.relationship("Expense", back_populates="category", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "budget_limit": float(self.budget_limit) if self.budget_limit else None,
        }


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    currency = db.Column(db.String(10), default="USD")
    notes = db.Column(db.Text)
    expense_type = db.Column(db.String(50), default="EXPENSE")
    spent_at = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="expenses")
    category = db.relationship("Category", back_populates="expenses")
    account = db.relationship("Account", back_populates="expenses")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "account_id": self.account_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "notes": self.notes,
            "description": self.notes or "Transaction",
            "expense_type": self.expense_type,
            "date": self.spent_at.isoformat() if self.spent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Bill(db.Model):
    __tablename__ = "bills"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    currency = db.Column(db.String(10), default="USD")
    cadence = db.Column(db.Enum(CadenceEnum), nullable=False, default=CadenceEnum.MONTHLY)
    next_due_date = db.Column(db.Date, nullable=False)
    channel_email = db.Column(db.Boolean, default=False)
    channel_whatsapp = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="bills")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "amount": float(self.amount),
            "currency": self.currency,
            "cadence": self.cadence.value,
            "next_due_date": self.next_due_date.isoformat() if self.next_due_date else None,
            "channel_email": self.channel_email,
            "channel_whatsapp": self.channel_whatsapp,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Reminder(db.Model):
    __tablename__ = "reminders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=True)
    message = db.Column(db.Text)
    remind_at = db.Column(db.DateTime)
    channel = db.Column(db.String(50), default="email")
    sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="reminders")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "bill_id": self.bill_id,
            "message": self.message,
            "remind_at": self.remind_at.isoformat() if self.remind_at else None,
            "channel": self.channel,
            "sent": self.sent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }