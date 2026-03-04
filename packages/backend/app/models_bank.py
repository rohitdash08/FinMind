"""
Bank sync models for storing bank connection information.
"""

from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from .extensions import db


class BankConnection(db.Model):
    """Stores user's bank connections."""
    __tablename__ = "bank_connections"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)  # mock, plaid, etc.
    institution_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="connected")
    access_token: Mapped[str] = mapped_column(Text, nullable=True)  # encrypted token
    refresh_token: Mapped[str] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", backref="bank_connections")
    
    def __repr__(self):
        return f"<BankConnection {self.institution_name} - {self.account_name}>"


class BankTransactionImport(db.Model):
    """Tracks imported transactions to avoid duplicates."""
    __tablename__ = "bank_transaction_imports"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(Integer, ForeignKey("bank_connections.id"), nullable=False)
    external_transaction_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    connection = db.relationship("BankConnection", backref="imported_transactions")
    
    def __repr__(self):
        return f"<BankTransactionImport {self.external_transaction_id}>"
