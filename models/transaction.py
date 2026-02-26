"""Data models for bank sync: Transaction, Account, Balance."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AccountType(str, Enum):
    """Supported bank account types."""
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"
    INVESTMENT = "investment"
    LOAN = "loan"
    OTHER = "other"


class TransactionStatus(str, Enum):
    """Transaction processing status."""
    PENDING = "pending"
    POSTED = "posted"
    CANCELLED = "cancelled"


class TransactionType(str, Enum):
    """Transaction type classification."""
    DEBIT = "debit"
    CREDIT = "credit"
    TRANSFER = "transfer"
    FEE = "fee"
    INTEREST = "interest"
    OTHER = "other"


class Currency(str, Enum):
    """Common currency codes."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"
    JPY = "JPY"


@dataclass
class Account:
    """Represents a bank account."""
    account_id: str
    name: str
    account_type: AccountType
    currency: Currency = Currency.USD
    institution_name: str = ""
    mask: str = ""  # Last 4 digits
    official_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not self.account_id:
            self.account_id = str(uuid.uuid4())


@dataclass
class Transaction:
    """Represents a financial transaction."""
    transaction_id: str
    account_id: str
    amount: float
    date: datetime
    description: str
    transaction_type: TransactionType = TransactionType.OTHER
    status: TransactionStatus = TransactionStatus.POSTED
    currency: Currency = Currency.USD
    category: str = ""
    merchant_name: str = ""
    pending: bool = False
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not self.transaction_id:
            self.transaction_id = str(uuid.uuid4())

    @property
    def is_debit(self) -> bool:
        return self.amount < 0

    @property
    def is_credit(self) -> bool:
        return self.amount > 0


@dataclass
class Balance:
    """Represents an account balance snapshot."""
    account_id: str
    current: float
    available: Optional[float] = None
    limit: Optional[float] = None
    currency: Currency = Currency.USD
    as_of: datetime = field(default_factory=datetime.utcnow)

    @property
    def utilization(self) -> Optional[float]:
        """Credit utilization ratio (for credit accounts)."""
        if self.limit and self.limit > 0:
            return round(abs(self.current) / self.limit, 4)
        return None
