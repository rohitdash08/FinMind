"""
Bank Sync Connector — Abstract Base Class

Defines the pluggable interface for bank integrations.
All connectors (Mock, Plaid, Teller, etc.) must inherit from this class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class TransactionRecord:
    """Normalized transaction record returned by any connector."""
    transaction_id: str
    date: date
    amount: float  # negative = debit/expense, positive = credit/income
    description: str
    category_id: Optional[int] = None
    currency: str = "USD"
    merchant: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_import_dict(self) -> Dict[str, Any]:
        """Convert to format expected by FinMind expense import."""
        return {
            "date": self.date.isoformat(),
            "amount": abs(self.amount),
            "description": self.description,
            "category_id": self.category_id,
            "expense_type": "INCOME" if self.amount > 0 else "EXPENSE",
            "currency": self.currency,
        }


@dataclass
class AccountInfo:
    """Bank account information."""
    account_id: str
    name: str
    type: str  # checking, savings, credit, etc.
    balance: float
    currency: str = "USD"
    masked_number: Optional[str] = None


@dataclass
class SyncResult:
    """Result of an import or refresh operation."""
    provider: str
    status: str  # success, partial, error
    transactions_imported: int
    transactions_skipped: int = 0
    error: Optional[str] = None
    accounts: List[AccountInfo] = field(default_factory=list)


class BankConnector(ABC):
    """
    Abstract base class for all bank connectors.

    Subclasses must implement:
    - connect(): Establish connection with bank
    - import_transactions(): Initial bulk import
    - refresh(): Incremental refresh since last sync
    """

    provider_name: str = ""
    description: str = ""

    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.credentials = credentials or {}
        self.connected = False

    @abstractmethod
    async def connect(self) -> ConnectionStatus:
        """
        Establish connection with the bank.
        Returns connection status.
        """

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the bank and clean up credentials.
        """

    @abstractmethod
    async def import_transactions(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> SyncResult:
        """
        Bulk import transactions for a given date range.
        Used for initial sync or full re-import.

        Args:
            account_id: The bank account identifier
            start_date: Start of import range (default: 90 days ago)
            end_date: End of import range (default: today)

        Returns:
            SyncResult with imported transaction count
        """

    @abstractmethod
    async def refresh(
        self,
        account_id: str,
        since: Optional[date] = None,
    ) -> SyncResult:
        """
        Incremental refresh — fetch only new/updated transactions.

        Args:
            account_id: The bank account identifier
            since: Fetch transactions since this date (default: last sync)

        Returns:
            SyncResult with new/updated transaction count
        """

    async def get_accounts(self) -> List[AccountInfo]:
        """
        List available accounts for the connected credentials.
        Default: raises NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support get_accounts()"
        )

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the connector is operational.
        Default: basic connectivity test.
        """
        try:
            status = await self.connect()
            return {
                "provider": self.provider_name,
                "status": status.value,
                "healthy": status == ConnectionStatus.CONNECTED,
            }
        except Exception as e:
            return {
                "provider": self.provider_name,
                "status": "error",
                "healthy": False,
                "error": str(e),
            }
