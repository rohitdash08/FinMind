from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import Numeric
from app.extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    preferred_currency = db.Column(db.String(3), default="INR")
    expenses = db.relationship("Expense", back_populates="user", lazy=True)
    bills = db.relationship("Bill", back_populates="user", lazy=True)
    categories = db.relationship("Category", back_populates="user", lazy=True)

    def __repr__(self):
        return f"<User {self.email}>"

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)

    user = db.relationship("User", back_populates="categories")

    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='uq_user_category_name'),)

    def __repr__(self):
        return f"<Category {self.name}>"

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    next_due_date = db.Column(db.Date, nullable=False)
    cadence = db.Column(db.String(50), nullable=False)
    channel_email = db.Column(db.Boolean, default=False)
    channel_whatsapp = db.Column(db.Boolean, default=False)
    autopay_enabled = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="bills")

    def __repr__(self):
        return f"<Bill {self.name}>"

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    description = db.Column(db.String(255))
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    expense_type = db.Column(db.String(50), nullable=False, default="EXPENSE")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)

    user = db.relationship("User", back_populates="expenses")
    category = db.relationship("Category")

    def __repr__(self):
        return f"<Expense {self.description} {self.amount}>"
