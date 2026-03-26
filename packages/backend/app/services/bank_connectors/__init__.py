"""
Pluggable bank connector architecture.

Provides a standardized interface for integrating with various bank APIs
to import and refresh financial transaction data.

Architecture:
    - BankConnector: Abstract base class defining the connector contract
    - ConnectorRegistry: Singleton registry for managing available connectors
    - MockBankConnector: Test connector with simulated data
    - BankConnection model: Stores per-user bank connection configurations

Usage:
    from app.services.bank_connectors import connector_registry, BankConnector

    # List available connectors
    connectors = connector_registry.list_connectors()

    # Get a specific connector
    conn = connector_registry.get("mock")
"""
from .base import (
    BankConnector,
    Transaction,
    Account,
    AccountType,
    TransactionType,
    ConnectorError,
    AuthenticationError,
    AccountNotFoundError,
    RateLimitError,
    ConnectorAuthStatus,
)
from .registry import ConnectorRegistry, ConnectorNotFoundError
from .mock import MockBankConnector

connector_registry = ConnectorRegistry()

# Auto-register built-in connectors
connector_registry.register("mock", MockBankConnector)

__all__ = [
    "BankConnector",
    "Transaction",
    "Account",
    "AccountType",
    "TransactionType",
    "ConnectorError",
    "AuthenticationError",
    "AccountNotFoundError",
    "RateLimitError",
    "ConnectorAuthStatus",
    "ConnectorNotFoundError",
    "ConnectorRegistry",
    "connector_registry",
    "MockBankConnector",
]
