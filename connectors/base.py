"""Abstract base class for bank connectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from models.transaction import Account, Balance, Transaction

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Base exception for connector errors."""
    pass


class AuthenticationError(ConnectorError):
    """Raised when authentication fails."""
    pass


class RateLimitError(ConnectorError):
    """Raised when API rate limit is hit."""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ConnectionError(ConnectorError):
    """Raised when connection to bank API fails."""
    pass


class BankConnector(ABC):
    """Abstract base class defining the bank connector interface.

    All bank integrations must implement this interface. It provides
    a standard contract for connecting to banks, importing transactions,
    refreshing data, and managing accounts.

    Usage:
        class MyBankConnector(BankConnector):
            ...

        connector = MyBankConnector(connector_id="my-bank-1", config={...})
        connector.connect()
        accounts = connector.get_accounts()
        transactions = connector.import_transactions(start, end)
        connector.disconnect()
    """

    def __init__(self, connector_id: str, config: Optional[dict] = None):
        self.connector_id = connector_id
        self.config = config or {}
        self._connected = False
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable connector name."""
        ...

    @property
    @abstractmethod
    def connector_type(self) -> str:
        """Unique type identifier (e.g., 'plaid', 'csv', 'mock')."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the bank/data source.

        Raises:
            AuthenticationError: If credentials are invalid.
            ConnectionError: If the service is unreachable.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection and release resources."""
        ...

    @abstractmethod
    def get_accounts(self) -> List[Account]:
        """List all connected accounts.

        Returns:
            List of Account objects.

        Raises:
            ConnectorError: If not connected or request fails.
        """
        ...

    @abstractmethod
    def get_balance(self, account_id: str) -> Balance:
        """Get current balance for an account.

        Args:
            account_id: The account identifier.

        Returns:
            Balance snapshot.

        Raises:
            ConnectorError: If account not found or request fails.
        """
        ...

    @abstractmethod
    def import_transactions(
        self, start_date: datetime, end_date: datetime, account_id: Optional[str] = None
    ) -> List[Transaction]:
        """Import transactions within a date range.

        Args:
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).
            account_id: Optional filter to a specific account.

        Returns:
            List of Transaction objects.

        Raises:
            ConnectorError: If import fails.
        """
        ...

    @abstractmethod
    def refresh(self) -> List[Transaction]:
        """Refresh/sync the latest transactions since last sync.

        Returns:
            List of new or updated Transaction objects.

        Raises:
            ConnectorError: If refresh fails.
        """
        ...

    def _ensure_connected(self) -> None:
        """Guard method to verify connection is active."""
        if not self._connected:
            raise ConnectorError(f"Connector '{self.connector_id}' is not connected. Call connect() first.")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.connector_id!r} connected={self._connected}>"
