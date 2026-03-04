"""
Bank Connectors - Pluggable architecture for bank integrations.

This module provides a standardized interface for connecting to various
banking APIs and services.

Usage:
    from app.services.bank_connectors import get_connector
    
    connector = get_connector('mock')  # Use mock for testing
    accounts = await connector.get_accounts(api_key='test-key')
    transactions = await connector.get_transactions(account_id='123')
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class ConnectorType(str, Enum):
    """Supported bank connector types."""
    MOCK = "mock"
    PLAID = "plaid"
    MONZO = "monzo"
    REVOLUT = "revolut"


@dataclass
class BankAccount:
    """Represents a bank account."""
    account_id: str
    account_name: str
    account_type: str  # checking, savings, credit
    balance: Decimal
    currency: str
    institution_name: str
    last_updated: datetime


@dataclass
class Transaction:
    """Represents a bank transaction."""
    transaction_id: str
    account_id: str
    amount: Decimal
    currency: str
    date: date
    description: str
    category: str | None = None
    merchant_name: str | None = None


class BankConnector(ABC):
    """Abstract base class for bank connectors."""
    
    def __init__(self, api_key: str | None = None, **config):
        self.api_key = api_key
        self.config = config
    
    @abstractmethod
    def get_accounts(self) -> list[BankAccount]:
        """Fetch all accounts linked to this connector."""
        pass
    
    @abstractmethod
    def get_transactions(
        self,
        account_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Transaction]:
        """Fetch transactions for a specific account."""
        pass
    
    @abstractmethod
    def refresh_account(self, account_id: str) -> BankAccount:
        """Refresh a specific account's balance."""
        pass
    
    @property
    @abstractmethod
    def connector_type(self) -> ConnectorType:
        """Return the type of connector."""
        pass
    
    def test_connection(self) -> bool:
        """Test the connection to the bank API."""
        try:
            self.get_accounts()
            return True
        except Exception:
            return False


# Registry of available connectors
_CONNECTORS: dict[ConnectorType, type[BankConnector]] = {}


def register_connector(connector_type: ConnectorType):
    """Decorator to register a bank connector."""
    def decorator(cls: type[BankConnector]):
        _CONNECTORS[connector_type] = cls
        return cls
    return decorator


def get_connector(
    connector_type: ConnectorType | str,
    api_key: str | None = None,
    **config,
) -> BankConnector:
    """Factory function to get a bank connector instance."""
    if isinstance(connector_type, str):
        connector_type = ConnectorType(connector_type)
    
    if connector_type not in _CONNECTORS:
        raise ValueError(f"Unknown connector type: {connector_type}")
    
    return _CONNECTORS[connector_type](api_key=api_key, **config)