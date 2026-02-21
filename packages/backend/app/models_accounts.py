# Multi-account models for financial account management
from datetime import datetime
from .extensions import db
from enum import Enum


class AccountType(str, Enum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CREDIT_CARD = "CREDIT_CARD"
    CASH = "CASH"
    INVESTMENT = "INVESTMENT"
    OTHER = "OTHER"


class FinancialAccount(db.Model):
    """User's financial accounts (bank, cash, credit card, etc.)"""
    __tablename__ = "financial_accounts"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(20), default="CHECKING", nullable=False)
    balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    institution = db.Column(db.String(200), nullable=True)  # Bank name
    account_number_last4 = db.Column(db.String(4), nullable=True)  # Last 4 digits for display
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    color = db.Column(db.String(7), nullable=True)  # Hex color for UI
    icon = db.Column(db.String(50), nullable=True)  # Icon name
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", backref="financial_accounts")
    
    @property
    def formatted_balance(self):
        """Return formatted balance with currency."""
        return f"{self.currency} {float(self.balance):,.2f}"
