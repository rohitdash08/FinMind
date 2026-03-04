"""
Bank Sync Connector - Pluggable architecture for bank integrations.

This module provides a base connector interface and implementations
for various bank integrations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("finmind.bank_connector")


class ConnectionStatus(str, Enum):
    """Bank connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


@dataclass
class BankTransaction:
    """Represents a bank transaction."""
    external_id: str
    date: datetime
    description: str
    amount: float
    currency: str
    category: Optional[str] = None
    merchant: Optional[str] = None
    pending: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class BankAccount:
    """Represents a bank account."""
    account_id: str
    account_name: str
    account_type: str  # checking, savings, credit
    balance: float
    currency: str
    institution_name: str
    last_updated: datetime


class BaseBankConnector(ABC):
    """Base class for all bank connectors."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._status = ConnectionStatus.DISCONNECTED
        self._last_error: Optional[str] = None
    
    @property
    def status(self) -> ConnectionStatus:
        return self._status
    
    @property
    def last_error(self) -> Optional[str]:
        return self._last_error
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the bank API.
        Returns True if successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the bank API."""
        pass
    
    @abstractmethod
    def get_accounts(self) -> List[BankAccount]:
        """Get list of connected bank accounts."""
        pass
    
    @abstractmethod
    def get_transactions(
        self, 
        account_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BankTransaction]:
        """Get transactions for a specific account."""
        pass
    
    @abstractmethod
    def refresh(self) -> bool:
        """Refresh the connection/credentials."""
        pass
    
    def validate_config(self) -> bool:
        """Validate the connector configuration."""
        return True


class MockBankConnector(BaseBankConnector):
    """Mock connector for testing and development."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._mock_accounts = config.get("mock_accounts", [
            {
                "account_id": "CHK001",
                "account_name": "Primary Checking",
                "account_type": "checking",
                "balance": 5432.10,
                "currency": "USD",
                "institution_name": "Mock Bank"
            },
            {
                "account_id": "SAV001", 
                "account_name": "Savings Account",
                "account_type": "savings",
                "balance": 12500.00,
                "currency": "USD",
                "institution_name": "Mock Bank"
            }
        ])
        self._mock_transactions = config.get("mock_transactions", [
            {
                "external_id": "TXN001",
                "date": datetime(2026, 3, 1),
                "description": "Grocery Store",
                "amount": -125.50,
                "currency": "USD",
                "category": "food",
                "merchant": "Whole Foods"
            },
            {
                "external_id": "TXN002",
                "date": datetime(2026, 3, 2),
                "description": "Salary Deposit",
                "amount": 3500.00,
                "currency": "USD",
                "category": "income",
                "merchant": "Employer Inc"
            },
            {
                "external_id": "TXN003",
                "date": datetime(2026, 3, 3),
                "description": "Electric Bill",
                "amount": -89.99,
                "currency": "USD",
                "category": "utilities",
                "merchant": "City Power"
            },
            {
                "external_id": "TXN004",
                "date": datetime(2026, 3, 4),
                "description": "Coffee Shop",
                "amount": -5.75,
                "currency": "USD",
                "category": "food",
                "merchant": "Starbucks"
            }
        ])
    
    def connect(self) -> bool:
        """Simulate connection."""
        logger.info("Mock bank connector connecting...")
        self._status = ConnectionStatus.CONNECTED
        return True
    
    def disconnect(self) -> bool:
        """Simulate disconnection."""
        self._status = ConnectionStatus.DISCONNECTED
        return True
    
    def get_accounts(self) -> List[BankAccount]:
        """Return mock accounts."""
        return [
            BankAccount(
                account_id=acc["account_id"],
                account_name=acc["account_name"],
                account_type=acc["account_type"],
                balance=acc["balance"],
                currency=acc["currency"],
                institution_name=acc["institution_name"],
                last_updated=datetime.utcnow()
            )
            for acc in self._mock_accounts
        ]
    
    def get_transactions(
        self,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BankTransaction]:
        """Return mock transactions."""
        transactions = []
        for txn in self._mock_transactions:
            tx = BankTransaction(
                external_id=txn["external_id"],
                date=txn["date"],
                description=txn["description"],
                amount=txn["amount"],
                currency=txn["currency"],
                category=txn.get("category"),
                merchant=txn.get("merchant")
            )
            
            # Filter by date range if provided
            if start_date and tx.date < start_date:
                continue
            if end_date and tx.date > end_date:
                continue
                
            transactions.append(tx)
        
        return transactions
    
    def refresh(self) -> bool:
        """Simulate refresh."""
        logger.info("Mock bank connector refreshing...")
        return True


# Registry of available connectors
CONNECTOR_REGISTRY: Dict[str, type] = {
    "mock": MockBankConnector,
}


def get_connector(connector_type: str, config: Dict[str, Any]) -> BaseBankConnector:
    """
    Factory function to get a bank connector instance.
    
    Args:
        connector_type: Type of connector (e.g., 'mock', 'plaid', 'stripe')
        config: Configuration for the connector
        
    Returns:
        Instance of the requested connector
        
    Raises:
        ValueError: If connector type is not supported
    """
    if connector_type not in CONNECTOR_REGISTRY:
        raise ValueError(
            f"Unknown connector type: {connector_type}. "
            f"Available: {list(CONNECTOR_REGISTRY.keys())}"
        )
    
    connector_class = CONNECTOR_REGISTRY[connector_type]
    return connector_class(config)


def register_connector(connector_type: str, connector_class: type) -> None:
    """
    Register a new connector type.
    
    Args:
        connector_type: Unique identifier for the connector
        connector_class: Class implementing BaseBankConnector
    """
    if not issubclass(connector_class, BaseBankConnector):
        raise TypeError("Connector must inherit from BaseBankConnector")
    
    CONNECTOR_REGISTRY[connector_type] = connector_class
    logger.info(f"Registered new connector: {connector_type}")
