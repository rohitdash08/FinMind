"""Bank Sync Connector Architecture.

Pluggable interface for bank integrations. Each provider implements
the BankConnector abstract class. The registry allows dynamic
registration and lookup of connectors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@dataclass
class BankAccountInfo:
    """Represents a bank account from the provider."""
    external_id: str
    name: str
    account_type: str  # checking, savings, credit, etc.
    currency: str
    balance: Decimal


@dataclass
class BankTransactionData:
    """Represents a transaction from the provider."""
    external_id: str
    amount: Decimal
    currency: str
    description: str
    category: Optional[str]
    transaction_date: date


class BankConnector(ABC):
    """Abstract base class for bank integrations.

    To add a new bank provider:
    1. Create a class that inherits from BankConnector
    2. Implement all abstract methods
    3. Register it with ConnectorRegistry.register()
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this provider (e.g., 'plaid', 'teller')."""
        ...

    @abstractmethod
    def authenticate(self, credentials: dict) -> dict:
        """Authenticate with the provider.

        Args:
            credentials: Provider-specific credentials (API keys, tokens, etc.)

        Returns:
            Connection metadata to store (e.g., access tokens).
        """
        ...

    @abstractmethod
    def list_accounts(self, connection_data: dict) -> list[BankAccountInfo]:
        """List available bank accounts.

        Args:
            connection_data: Stored connection metadata from authenticate().

        Returns:
            List of available bank accounts.
        """
        ...

    @abstractmethod
    def fetch_transactions(
        self,
        connection_data: dict,
        account_id: str,
        from_date: date,
        to_date: date,
    ) -> list[BankTransactionData]:
        """Fetch transactions for a specific account.

        Args:
            connection_data: Stored connection metadata.
            account_id: External account ID.
            from_date: Start date (inclusive).
            to_date: End date (inclusive).

        Returns:
            List of transactions in the date range.
        """
        ...

    @abstractmethod
    def refresh_connection(self, connection_data: dict) -> dict:
        """Refresh the connection (e.g., refresh OAuth tokens).

        Args:
            connection_data: Current stored connection metadata.

        Returns:
            Updated connection metadata.
        """
        ...


class ConnectorRegistry:
    """Registry for bank connector providers."""

    _connectors: dict[str, type[BankConnector]] = {}

    @classmethod
    def register(cls, connector_class: type[BankConnector]) -> type[BankConnector]:
        """Register a connector. Can be used as a decorator."""
        instance = connector_class()
        cls._connectors[instance.provider_name] = connector_class
        return connector_class

    @classmethod
    def get(cls, provider: str) -> BankConnector:
        """Get an instance of a registered connector."""
        if provider not in cls._connectors:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Available: {list(cls._connectors.keys())}"
            )
        return cls._connectors[provider]()

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._connectors.keys())
