import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class User(db.Model):
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    preferred_currency = db.Column(db.String(3), default="INR", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.email}>"


class Category(db.Model):
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    budget = db.Column(db.Float, nullable=True) # New: budget limit for the category
    budget_currency = db.Column(db.String(3), nullable=True) # New: currency for the budget
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("categories", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="_user_name_uc"),
    )

    def __repr__(self):
        return f"<Category {self.name}>"


class Bill(db.Model):
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR") # Default currency
    next_due_date = db.Column(db.Date, nullable=False)
    cadence = db.Column(db.String(50), nullable=False)  # e.g., MONTHLY, ANNUALLY
    channel_email = db.Column(db.Boolean, default=False)
    channel_whatsapp = db.Column(db.Boolean, default=False)
    autopay_enabled = db.Column(db.Boolean, default=False)
    paid_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category_id = db.Column(UUID(as_uuid=True), db.ForeignKey("category.id"), nullable=True) # New: link to category

    user = db.relationship("User", backref=db.backref("bills", lazy=True))
    category = db.relationship("Category", backref=db.backref("bills", lazy=True))

    def __repr__(self):
        return f"<Bill {self.name}>"

