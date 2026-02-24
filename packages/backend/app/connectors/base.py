"""Abstract base class for bank sync connectors.

Every bank integration (mock, Setu AA, direct bank API, etc.) must
implement :class:`BankConnector`.  The interface is deliberately small so
that adding a new provider is a single-file job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


# ------------------------------------------------------------------
# Value objects
# ------------------------------------------------------------------


class AccountType(str, Enum):
    SAVINGS = "SAVINGS"
    CURRENT = "CURRENT"
    CREDIT_CARD = "CREDIT_CARD"
    LOAN = "LOAN"
    OTHER = "OTHER"


class TransactionStatus(str, Enum):
    POSTED = "POSTED"
    PENDING = "PENDING"


class SyncStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


@dataclass
class BankAccount:
    """Normalised representation of a bank account."""

    external_id: str
    name: str
    account_type: AccountType = AccountType.SAVINGS
    balance: Decimal = Decimal("0.00")
    currency: str = "INR"
    masked_number: str = ""


@dataclass
class BankTransaction:
    """Normalised representation of a single transaction."""

    external_id: str
    date: date
    amount: Decimal
    description: str
    currency: str = "INR"
    category_hint: str | None = None
    status: TransactionStatus = TransactionStatus.POSTED
    reference: str = ""


@dataclass
class SyncResult:
    """Value returned by import/refresh operations."""

    status: SyncStatus = SyncStatus.SUCCESS
    accounts: list[BankAccount] = field(default_factory=list)
    transactions: list[BankTransaction] = field(default_factory=list)
    cursor: str | None = None
    error: str | None = None
    synced_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def transaction_count(self) -> int:
        return len(self.transactions)


# ------------------------------------------------------------------
# Abstract connector
# ------------------------------------------------------------------


class BankConnector(ABC):
    """Interface that every bank connector must implement.

    Lifecycle::

        connector = SomeConnector(config)
        connector.authenticate(credentials)
        result = connector.import_transactions(account_id, start, end)

        # later …
        result = connector.refresh(account_id, cursor)
    """

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Validate / exchange credentials.  Return True on success."""

    @abstractmethod
    def get_accounts(self) -> list[BankAccount]:
        """Return the list of accounts available after authentication."""

    @abstractmethod
    def import_transactions(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> SyncResult:
        """Full import of transactions for the given date window."""

    @abstractmethod
    def refresh(
        self,
        account_id: str,
        cursor: str | None = None,
    ) -> SyncResult:
        """Incremental refresh since *cursor*.

        If *cursor* is ``None`` the connector should fall back to a
        sensible default (e.g. last 30 days).
        """

    # Optional hook — connectors may override for cleanup.
    def disconnect(self) -> None:  # pragma: no cover
        """Release any resources held by the connector."""
