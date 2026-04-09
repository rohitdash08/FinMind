from datetime import datetime
from ..extensions import db


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships with cascade delete
    expenses = db.relationship(
        "Expense", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    bills = db.relationship(
        "Bill", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    categories = db.relationship(
        "Category", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    reminders = db.relationship(
        "Reminder", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self, include_sensitive=False):
        data = {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        # password_hash is sensitive and not included in export
        return data


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    expense_date = db.Column(db.Date, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id")) # No cascade for category if user delete
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "description": self.description,
            "expense_date": self.expense_date.isoformat(),
            "category_id": self.category_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Bill(db.Model):
    __tablename__ = "bills"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    next_due_date = db.Column(db.Date, nullable=False)
    cadence = db.Column(db.String(50), nullable=False)  # e.g., "MONTHLY", "WEEKLY"
    channel_email = db.Column(db.Boolean, default=False)
    channel_whatsapp = db.Column(db.Boolean, default=False)
    autopay_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "amount": self.amount,
            "next_due_date": self.next_due_date.isoformat(),
            "cadence": self.cadence,
            "channel_email": self.channel_email,
            "channel_whatsapp": self.channel_whatsapp,
            "autopay_enabled": self.autopay_enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (db.UniqueConstraint("user_id", "name", name="_user_category_uc"),)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Reminder(db.Model):
    __tablename__ = "reminders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True) # When the reminder was actually sent
    status = db.Column(db.String(50), default="SCHEDULED") # e.g., SCHEDULED, SENT, DISMISSED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "bill_id": self.bill_id,
            "due_date": self.due_date.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
