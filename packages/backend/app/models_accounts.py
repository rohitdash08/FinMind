"""Multi-account financial models for FinMind.

Supports multiple financial account types:
- Checking, Savings, Credit Card, Cash, Investment, Loan
- Account balance tracking
- Transfer between accounts
"""

from datetime import datetime, timezone
from ..extensions import db


class Account(db.Model):
    """User financial account."""
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(20), nullable=False, default="checking")  # checking, savings, credit_card, cash, investment, loan
    currency = db.Column(db.String(3), default="USD")
    balance = db.Column(db.Float, default=0.0)
    credit_limit = db.Column(db.Float, nullable=True)  # For credit cards
    interest_rate = db.Column(db.Float, nullable=True)  # For loans/savings
    is_active = db.Column(db.Boolean, default=True)
    color = db.Column(db.String(7), nullable=True)  # Hex color for UI
    icon = db.Column(db.String(50), nullable=True)  # Icon identifier
    institution = db.Column(db.String(100), nullable=True)  # Bank name
    last_synced = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = db.relationship("User", backref=db.backref("accounts", lazy="dynamic"))

    ACCOUNT_TYPES = ["checking", "savings", "credit_card", "cash", "investment", "loan"]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "account_type": self.account_type,
            "currency": self.currency,
            "balance": self.balance,
            "credit_limit": self.credit_limit,
            "interest_rate": self.interest_rate,
            "is_active": self.is_active,
            "color": self.color,
            "icon": self.icon,
            "institution": self.institution,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def available_balance(self):
        """Get available balance (considering credit limits)."""
        if self.account_type == "credit_card" and self.credit_limit:
            return self.credit_limit + self.balance  # balance is negative for CC
        return self.balance


class AccountTransfer(db.Model):
    """Transfer between accounts."""
    __tablename__ = "account_transfers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    from_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    to_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default="USD")
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    from_account = db.relationship("Account", foreign_keys=[from_account_id])
    to_account = db.relationship("Account", foreign_keys=[to_account_id])

    def to_dict(self):
        return {
            "id": self.id,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "amount": self.amount,
            "currency": self.currency,
            "note": self.note,
            "from_account": self.from_account.name if self.from_account else None,
            "to_account": self.to_account.name if self.to_account else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
