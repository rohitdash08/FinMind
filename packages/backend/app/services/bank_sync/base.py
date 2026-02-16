"""
Base bank connector interface.

All bank integrations must implement this abstract class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional


class ConnectionStatus(str, Enum):
    """Status of a bank connection."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"
    REQUIRES_REAUTH = "requires_reauth"


class TransactionType(str, Enum):
    """Normalized transaction type."""
    DEBIT = "debit"
    CREDIT = "credit"
    TRANSFER = "transfer"


@dataclass
class BankAccount:
    """Normalized bank account representation."""
    account_id: str
    name: str
    institution_name: str
    account_type: str  # checking, savings, credit_card, etc.
    currency: str = "USD"
    balance: float = 0.0
    available_balance: Optional[float] = None
    last_synced: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class BankTransaction:
    """Normalized bank transaction representation."""
    transaction_id: str
    account_id: str
    amount: float
    currency: str
    description: str
    category: Optional[str] = None
    transaction_type: TransactionType = TransactionType.DEBIT
    date: date = field(default_factory=date.today)
    pending: bool = False
    merchant_name: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    """Result of a sync/import operation."""
    success: bool
    accounts_synced: int = 0
    transactions_imported: int = 0
    transactions_updated: int = 0
    errors: List[str] = field(default_factory=list)
    synced_at: datetime = field(default_factory=datetime.utcnow)


class BaseBankConnector(ABC):
    """
    Abstract base class for bank connectors.

    All bank integrations (Plaid, Yodlee, mock, etc.) must implement
    this interface to be compatible with the FinMind bank sync system.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'plaid', 'yodlee', 'mock')."""
        ...

    @abstractmethod
    def connect(self, credentials: dict) -> ConnectionStatus:
        """
        Establish a connection with the bank provider.

        Args:
            credentials: Provider-specific credentials (API keys, tokens, etc.)

        Returns:
            ConnectionStatus indicating the result.
        """
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the bank provider.

        Returns:
            True if successfully disconnected.
        """
        ...

    @abstractmethod
    def get_status(self) -> ConnectionStatus:
        """
        Get the current connection status.

        Returns:
            Current ConnectionStatus.
        """
        ...

    @abstractmethod
    def list_accounts(self) -> List[BankAccount]:
        """
        List all linked bank accounts.

        Returns:
            List of BankAccount objects.
        """
        ...

    @abstractmethod
    def import_transactions(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[BankTransaction]:
        """
        Import transactions from a specific account.

        Args:
            account_id: The account to import from.
            start_date: Start of date range (default: 30 days ago).
            end_date: End of date range (default: today).

        Returns:
            List of BankTransaction objects.
        """
        ...

    @abstractmethod
    def refresh(self, account_id: Optional[str] = None) -> SyncResult:
        """
        Refresh account data and import new transactions.

        Args:
            account_id: Specific account to refresh, or None for all.

        Returns:
            SyncResult with details of what was synced.
        """
        ...

    def get_account(self, account_id: str) -> Optional[BankAccount]:
        """
        Get a specific account by ID.

        Default implementation filters list_accounts().
        Can be overridden for more efficient lookups.
        """
        for account in self.list_accounts():
            if account.account_id == account_id:
                return account
        return None

    def supports_webhooks(self) -> bool:
        """Whether this connector supports webhook notifications."""
        return False

    def handle_webhook(self, payload: dict) -> SyncResult:
        """
        Handle an incoming webhook from the provider.

        Default implementation does nothing; override in providers
        that support webhooks.
        """
        return SyncResult(success=False, errors=["Webhooks not supported"])
