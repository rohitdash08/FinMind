"""Bank Sync Connector Interface and Implementations.

This module provides a pluggable architecture for bank integrations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class BankConnectionStatus(str, Enum):
    """Bank connection status."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"


@dataclass
class BankAccount:
    """Represents a bank account."""
    id: str
    name: str
    account_type: str  # CHECKING, SAVINGS, CREDIT_CARD, etc.
    currency: str
    balance: Decimal
    account_number_masked: Optional[str] = None
    institution_name: Optional[str] = None


@dataclass
class BankTransaction:
    """Represents a bank transaction."""
    id: str
    account_id: str
    date: date
    amount: Decimal  # Positive for credit, negative for debit
    description: str
    currency: str
    category: Optional[str] = None
    merchant_name: Optional[str] = None
    pending: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    """Result of a bank sync operation."""
    success: bool
    accounts_synced: int = 0
    transactions_synced: int = 0
    new_transactions: list[BankTransaction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    last_sync_at: Optional[datetime] = None


class BankConnector(ABC):
    """Abstract base class for bank connectors.
    
    All bank integrations must implement this interface.
    """
    
    def __init__(self, connector_id: str, name: str, config: dict[str, Any]):
        self.connector_id = connector_id
        self.name = name
        self.config = config
        self._authenticated = False
    
    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Authenticate with the bank API.
        
        Args:
            credentials: Bank-specific credentials (API keys, tokens, etc.)
            
        Returns:
            True if authentication successful
        """
        pass
    
    @abstractmethod
    def fetch_accounts(self) -> list[BankAccount]:
        """Fetch all accounts for the authenticated user.
        
        Returns:
            List of bank accounts
        """
        pass
    
    @abstractmethod
    def fetch_transactions(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> list[BankTransaction]:
        """Fetch transactions for a specific account.
        
        Args:
            account_id: The account ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of transactions
        """
        pass
    
    @abstractmethod
    def refresh(self) -> bool:
        """Refresh the connection (e.g., refresh tokens).
        
        Returns:
            True if refresh successful
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the bank API.
        
        Returns:
            True if disconnected successfully
        """
        pass
    
    @abstractmethod
    def get_connection_status(self) -> BankConnectionStatus:
        """Get current connection status.
        
        Returns:
            Connection status
        """
        pass
    
    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Check connector health.
        
        Returns:
            Health status information
        """
        pass
    
    def is_authenticated(self) -> bool:
        """Check if connector is authenticated."""
        return self._authenticated


class ConnectorRegistry:
    """Registry for bank connectors."""
    
    _connectors: dict[str, type[BankConnector]] = {}
    
    @classmethod
    def register(cls, connector_id: str, connector_class: type[BankConnector]) -> None:
        """Register a connector class.
        
        Args:
            connector_id: Unique identifier for the connector
            connector_class: The connector class to register
        """
        cls._connectors[connector_id] = connector_class
    
    @classmethod
    def get(cls, connector_id: str) -> Optional[type[BankConnector]]:
        """Get a connector class by ID.
        
        Args:
            connector_id: The connector identifier
            
        Returns:
            The connector class or None if not found
        """
        return cls._connectors.get(connector_id)
    
    @classmethod
    def list_connectors(cls) -> dict[str, type[BankConnector]]:
        """List all registered connectors.
        
        Returns:
            Dictionary of connector_id -> connector_class
        """
        return cls._connectors.copy()
    
    @classmethod
    def create_connector(
        cls,
        connector_id: str,
        config: dict[str, Any]
    ) -> Optional[BankConnector]:
        """Create an instance of a registered connector.
        
        Args:
            connector_id: The connector identifier
            config: Configuration for the connector
            
        Returns:
            Connector instance or None if not found
        """
        connector_class = cls._connectors.get(connector_id)
        if not connector_class:
            return None
        return connector_class(connector_id, config.get("name", connector_id), config)
