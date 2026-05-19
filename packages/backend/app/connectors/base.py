"""Base classes and interfaces for bank sync connectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class TransactionType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


@dataclass
class BankTransaction:
    """Normalized transaction from a bank connector.

    All connectors must return transactions in this format.
    """

    date: date
    amount: Decimal
    description: str
    transaction_type: TransactionType = TransactionType.DEBIT
    currency: str = "INR"
    reference_id: Optional[str] = None
    category_hint: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)

    def to_expense_dict(self, user_id: int) -> dict:
        """Convert to dict matching the Expense model."""
        return {
            "user_id": user_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "description": self.description[:500],
            "spent_at": self.date,
            "expense_type": "EXPENSE" if self.transaction_type == TransactionType.DEBIT else "INCOME",
            "notes": f"Imported via {self.__class__.__name__}",
        }


class BankConnector(ABC):
    """Abstract base for all bank integration connectors.

    Subclass and implement the abstract methods to add a new bank.
    """

    # Subclasses must set these
    name: str = ""
    display_name: str = ""

    @abstractmethod
    async def fetch_transactions(
        self,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        **credentials,
    ) -> list[BankTransaction]:
        """Fetch transactions from the bank for the given date range.

        Args:
            user_id: The FinMind user ID.
            from_date: Start date (inclusive). Defaults to 30 days ago.
            to_date: End date (inclusive). Defaults to today.
            **credentials: Bank-specific auth (api_key, access_token, etc.)

        Returns:
            List of normalized BankTransaction objects.
        """
        ...

    @abstractmethod
    async def refresh_connection(self, **credentials) -> bool:
        """Verify the connection is still valid. Return True if healthy."""
        ...

    @abstractmethod
    def get_connection_status(self) -> dict:
        """Return connection metadata for UI display."""
        ...

    def is_healthy(self) -> bool:
        """Default health check — override for custom logic."""
        return True
