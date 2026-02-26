"""Financial account models for multi-account support."""
from datetime import datetime
from enum import Enum
from .extensions import db


class AccountType(str, Enum):
    """Types of financial accounts."""
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CREDIT_CARD = "CREDIT_CARD"
    CASH = "CASH"
    INVESTMENT = "INVESTMENT"
    LOAN = "LOAN"
    OTHER = "OTHER"


class FinancialAccount(db.Model):
    """User's financial accounts (bank, cash, credit card, etc.)."""
    __tablename__ = "financial_accounts"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(20), default=AccountType.CHECKING.value, nullable=False)
    balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    institution = db.Column(db.String(200), nullable=True)
    account_number_last4 = db.Column(db.String(4), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    color = db.Column(db.String(7), nullable=True)
    icon = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "account_type": self.account_type,
            "balance": float(self.balance),
            "currency": self.currency,
            "institution": self.institution,
            "account_number_last4": self.account_number_last4,
            "is_active": self.is_active,
            "color": self.color,
            "icon": self.icon,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
