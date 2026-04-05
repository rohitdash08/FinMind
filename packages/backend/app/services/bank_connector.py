"""
Bank Connector Architecture

Provides a pluggable interface for bank integrations with support for:
- Importing transactions from bank APIs
- Refreshing/syncing new transactions
- Mock connector for testing
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class TransactionType(str, Enum):
    """Types of transactions supported by connectors."""
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"


@dataclass
class BankTransaction:
    """Represents a single transaction from a bank connector."""
    date: date
    amount: float
    description: str
    transaction_type: TransactionType = TransactionType.EXPENSE
    currency: str = "USD"
    category_id: int | None = None
    notes: str = ""
    external_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_expense_dict(self) -> dict[str, Any]:
        """Convert to expense API format."""
        expense_type = "INCOME" if self.transaction_type in (
            TransactionType.CREDIT,
            TransactionType.INCOME,
        ) else "EXPENSE"
        
        return {
            "date": self.date.isoformat(),
            "amount": abs(self.amount),
            "description": self.description[:500],
            "category_id": self.category_id,
            "expense_type": expense_type,
            "currency": self.currency[:10],
            "notes": self.notes[:500],
        }


@dataclass
class BankAccount:
    """Represents a bank account from a connector."""
    account_id: str
    account_name: str
    account_type: str  # checking, savings, credit, etc.
    currency: str = "USD"
    current_balance: float = 0.0
    available_balance: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorConfig:
    """Configuration for a bank connector."""
    connector_type: str
    user_id: int
    credentials: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    last_sync: datetime | None = None


class BankConnector(ABC):
    """
    Abstract base class for bank connectors.
    
    Implement this interface to create a new bank integration.
    """
    
    @property
    @abstractmethod
    def connector_type(self) -> str:
        """Unique identifier for this connector type."""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the connector."""
        pass
    
    @property
    def supported_features(self) -> list[str]:
        """List of supported features. Override in subclass."""
        return ["import", "refresh"]
    
    @abstractmethod
    def connect(self, config: ConnectorConfig) -> bool:
        """
        Establish connection to the bank API.
        
        Args:
            config: Connector configuration with credentials
            
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the bank API and clean up resources.
        
        Returns:
            True if disconnection successful
        """
        pass
    
    @abstractmethod
    def get_accounts(self) -> list[BankAccount]:
        """
        Retrieve all accounts linked to this connector.
        
        Returns:
            List of BankAccount objects
        """
        pass
    
    @abstractmethod
    def get_transactions(
        self,
        account_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[BankTransaction]:
        """
        Retrieve transactions for a specific account.
        
        Args:
            account_id: The account to fetch transactions for
            from_date: Start date for transaction retrieval
            to_date: End date for transaction retrieval
            
        Returns:
            List of BankTransaction objects
        """
        pass
    
    @abstractmethod
    def refresh_transactions(
        self,
        account_id: str,
        since: datetime,
    ) -> list[BankTransaction]:
        """
        Refresh transactions newer than the given datetime.
        
        Args:
            account_id: The account to refresh transactions for
            since: Only return transactions newer than this datetime
            
        Returns:
            List of new BankTransaction objects
        """
        pass
    
    def validate_credentials(self, credentials: dict[str, str]) -> bool:
        """
        Validate credentials before attempting connection.
        
        Override in subclass to provide custom validation.
        
        Args:
            credentials: Dictionary of credential values
            
        Returns:
            True if credentials are valid
        """
        return bool(credentials)
    
    def get_connection_status(self) -> dict[str, Any]:
        """
        Get current connection status.
        
        Override in subclass to provide detailed status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "connected": False,
            "connector_type": self.connector_type,
        }


class ConnectorRegistry:
    """
    Registry for managing bank connectors.
    
    Provides a central way to register and retrieve connectors.
    """
    
    _connectors: dict[str, type[BankConnector]] = {}
    _instances: dict[str, BankConnector] = {}
    
    @classmethod
    def register(cls, connector_class: type[BankConnector]) -> None:
        """Register a connector class."""
        instance = connector_class()
        cls._connectors[instance.connector_type] = connector_class
    
    @classmethod
    def get_connector(cls, connector_type: str) -> BankConnector | None:
        """Get a connector instance by type."""
        if connector_type not in cls._connectors:
            return None
        
        if connector_type not in cls._instances:
            cls._instances[connector_type] = cls._connectors[connector_type]()
        
        return cls._instances[connector_type]
    
    @classmethod
    def list_connectors(cls) -> list[dict[str, Any]]:
        """List all registered connectors."""
        result = []
        for connector_type, connector_class in cls._connectors.items():
            instance = connector_class()
            result.append({
                "connector_type": connector_type,
                "display_name": instance.display_name,
                "supported_features": instance.supported_features,
            })
        return result
    
    @classmethod
    def clear_instances(cls) -> None:
        """Clear all connector instances (useful for testing)."""
        cls._instances.clear()


def register_connector(connector_class: type[BankConnector]) -> None:
    """Decorator to register a connector class."""
    ConnectorRegistry.register(connector_class)
    return connector_class