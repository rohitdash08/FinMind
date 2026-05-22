from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime


class Transaction:
    """Represents a single bank transaction."""

    def __init__(
        self,
        transaction_id: str,
        amount: float,
        description: str,
        date: datetime,
        account_id: str,
        category: str = None,
        metadata: Dict[str, Any] = None,
    ):
        self.transaction_id = transaction_id
        self.amount = amount
        self.description = description
        self.date = date
        self.account_id = account_id
        self.category = category
        self.metadata = metadata or {}


class BaseBankConnector(ABC):
    """Abstract base class for all bank connectors."""

    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """Authenticate with the bank using provided credentials."""
        pass

    @abstractmethod
    def import_transactions(self, account_id: str, from_date: datetime, to_date: datetime) -> List[Transaction]:
        """Import transactions for a given account and date range."""
        pass

    @abstractmethod
    def refresh_accounts(self) -> List[Dict[str, Any]]:
        """Refresh and return list of accounts with updated balances."""
        pass