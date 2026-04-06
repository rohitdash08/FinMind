"""
Bank Sync Connector Architecture

This module provides a pluggable architecture for bank integrations.
Each connector implements the BaseConnector interface to provide
import and refresh functionality for bank transactions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any


class ConnectorType(str, Enum):
    """Supported connector types."""

    MOCK = "mock"
    # Future connectors can be added here:
    # PLAID = "plaid"
    # YODLEE = "yodlee"


@dataclass
class Transaction:
    """Represents a bank transaction."""

    date: date
    amount: float
    description: str
    category_id: int | None = None
    expense_type: str = "EXPENSE"
    currency: str = "USD"


@dataclass
class Account:
    """Represents a bank account."""

    account_id: str
    account_name: str
    account_type: str
    balance: float
    currency: str = "USD"


class BaseConnector(ABC):
    """
    Abstract base class for bank connectors.

    All connectors must implement the import_transactions and refresh methods.
    """

    @property
    @abstractmethod
    def connector_type(self) -> ConnectorType:
        """Return the type of connector."""
        pass

    @abstractmethod
    def import_transactions(
        self,
        user_id: int,
        account_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Transaction]:
        """
        Import transactions from the bank.

        Args:
            user_id: The user ID to import transactions for
            account_id: Optional specific account to import from
            from_date: Optional start date for transaction import
            to_date: Optional end date for transaction import

        Returns:
            List of Transaction objects
        """
        pass

    @abstractmethod
    def refresh(self, user_id: int) -> dict[str, Any]:
        """
        Refresh account data and fetch latest transactions.

        Args:
            user_id: The user ID to refresh data for

        Returns:
            Dictionary containing refresh status and any new transactions
        """
        pass

    @abstractmethod
    def get_accounts(self, user_id: int) -> list[Account]:
        """
        Get all accounts linked to this connector for a user.

        Args:
            user_id: The user ID to get accounts for

        Returns:
            List of Account objects
        """
        pass

    def validate_credentials(self) -> bool:
        """
        Validate that the connector has valid credentials.

        Returns:
            True if credentials are valid, False otherwise
        """
        return True


class ConnectorRegistry:
    """
    Registry for managing connector instances.

    This registry allows for dynamic connector selection and management.
    """

    _connectors: dict[ConnectorType, type[BaseConnector]] = {}

    @classmethod
    def register(cls, connector_type: ConnectorType) -> callable:
        """
        Decorator to register a connector class.

        Usage:
            @ConnectorRegistry.register(ConnectorType.MOCK)
            class MockConnector(BaseConnector):
                ...
        """

        def decorator(connector_class: type[BaseConnector]) -> type[BaseConnector]:
            cls._connectors[connector_type] = connector_class
            return connector_class

        return decorator

    @classmethod
    def get_connector(
        cls,
        connector_type: ConnectorType,
        **kwargs: Any,
    ) -> BaseConnector:
        """
        Get an instance of a connector by type.

        Args:
            connector_type: The type of connector to instantiate
            **kwargs: Additional arguments to pass to the connector constructor

        Returns:
            An instance of the requested connector

        Raises:
            ValueError: If the connector type is not registered
        """
        if connector_type not in cls._connectors:
            raise ValueError(
                f"Connector type '{connector_type}' is not registered. "
                f"Available types: {list(cls._connectors.keys())}"
            )
        return cls._connectors[connector_type](**kwargs)

    @classmethod
    def list_connectors(cls) -> list[ConnectorType]:
        """List all registered connector types."""
        return list(cls._connectors.keys())


# Import connectors to register them
from app.connectors.mock import MockConnector  # noqa: E402

# Register the mock connector
ConnectorRegistry.register(ConnectorType.MOCK)(MockConnector)
