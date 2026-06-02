"""Base Bank Connector Interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class ConnectionStatus(Enum):
    """Status of a bank connection."""
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"


@dataclass
class BankAccount:
    """Represents a bank account."""
    id: str
    name: str
    account_type: str
    currency: str
    balance: float
    available_balance: Optional[float] = None
    masked_number: Optional[str] = None
    institution_name: Optional[str] = None


@dataclass
class Transaction:
    """Represents a financial transaction."""
    id: str
    account_id: str
    amount: float
    currency: str
    description: str
    transaction_date: datetime
    posted_date: Optional[datetime] = None
    merchant_name: Optional[str] = None
    merchant_category: Optional[str] = None
    transaction_type: str = "debit"
    pending: bool = False


@dataclass
class ConnectionCredentials:
    """Credentials for connecting to a bank."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    additional_data: Optional[Dict[str, Any]] = None


class BankConnector(ABC):
    """Abstract base class for bank connectors."""
    
    name: str
    display_name: str
    description: str
    supported_countries: List[str]
    features: List[str]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
    
    @abstractmethod
    def connect(self, credentials: ConnectionCredentials) -> Dict[str, Any]:
        """Establish connection to the bank."""
        pass
    
    @abstractmethod
    def validate_credentials(self, credentials: ConnectionCredentials) -> bool:
        """Validate credentials are valid and not expired."""
        pass
    
    @abstractmethod
    def refresh_connection(self, credentials: ConnectionCredentials) -> ConnectionCredentials:
        """Refresh expired credentials."""
        pass
    
    @abstractmethod
    def get_accounts(self, credentials: ConnectionCredentials) -> List[BankAccount]:
        """Retrieve all accounts accessible through this connection."""
        pass
    
    @abstractmethod
    def get_transactions(
        self,
        credentials: ConnectionCredentials,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """Retrieve transactions for a specific account."""
        pass
    
    @abstractmethod
    def get_balance(self, credentials: ConnectionCredentials, account_id: str) -> BankAccount:
        """Get current balance for an account."""
        pass
    
    @abstractmethod
    def disconnect(self, credentials: ConnectionCredentials) -> bool:
        """Revoke the connection to the bank."""
        pass
    
    @abstractmethod
    def get_connection_status(self, credentials: ConnectionCredentials) -> ConnectionStatus:
        """Check the status of the connection."""
        pass


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class ConnectionError(Exception):
    """Raised when connection to bank fails."""
    pass


class AccountNotFoundError(Exception):
    """Raised when an account is not found."""
    pass
