"""
Bank Connector Interface and Base Classes

This module provides the pluggable architecture for bank integrations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable
import logging

logger = logging.getLogger("finmind.bank_connectors")


class ConnectorStatus(str, Enum):
    """Status of a bank connector"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    REFRESHING = "refreshing"
    ERROR = "error"


@dataclass
class TokenInfo:
    """OAuth token information"""
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    token_type: str = "Bearer"
    scope: str | None = None

    def is_expired(self) -> bool:
        """Check if token is expired or about to expire"""
        if self.expires_at is None:
            return False
        # Consider token expired if less than 5 minutes remaining
        return datetime.utcnow() >= self.expires_at.replace(tzinfo=None)


@dataclass
class Account:
    """Bank account information"""
    account_id: str
    account_name: str
    account_type: str  # checking, savings, credit, etc.
    currency: str = "USD"
    balance: Decimal | None = None
    available_balance: Decimal | None = None
    mask: str | None = None  # Last 4 digits
    institution_name: str | None = None
    institution_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Transaction:
    """Bank transaction"""
    transaction_id: str
    account_id: str
    amount: Decimal
    date: date
    description: str
    currency: str = "USD"
    merchant_name: str | None = None
    category: str | None = None
    pending: bool = False
    transaction_type: str = "debit"  # debit, credit
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorConfig:
    """Configuration for a bank connector"""
    user_id: int
    institution_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    item_id: str | None = None  # External ID from bank
    status: ConnectorStatus = ConnectorStatus.DISCONNECTED
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BankConnector(Protocol):
    """
    Protocol defining the interface for bank connectors.
    
    All bank connectors must implement these methods to be compatible
    with the FinMind bank sync system.
    """

    @property
    def institution_id(self) -> str:
        """Unique identifier for the financial institution"""
        ...

    @property
    def institution_name(self) -> str:
        """Display name for the financial institution"""
        ...

    @property
    def supports_oauth(self) -> bool:
        """Whether this connector supports OAuth flow"""
        ...

    @property
    def supports_refresh(self) -> bool:
        """Whether this connector supports token refresh"""
        ...

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get OAuth authorization URL"""
        ...

    def exchange_code(self, code: str, redirect_uri: str) -> TokenInfo:
        """Exchange authorization code for tokens"""
        ...

    def refresh_token(self, token_info: TokenInfo) -> TokenInfo:
        """Refresh an expired token"""
        ...

    def get_accounts(self, token_info: TokenInfo) -> list[Account]:
        """Fetch accounts for the connected user"""
        ...

    def get_transactions(
        self,
        token_info: TokenInfo,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Transaction]:
        """Fetch transactions for an account"""
        ...

    def disconnect(self, token_info: TokenInfo | None = None) -> bool:
        """Disconnect and revoke access"""
        ...


class BaseBankConnector(ABC):
    """
    Abstract base class for bank connectors.
    
    Provides common functionality and enforces the interface.
    """

    def __init__(self, config: ConnectorConfig | None = None):
        self._config = config or ConnectorConfig(
            user_id=0,
            institution_id=self.institution_id
        )
        self._logger = logging.getLogger(f"finmind.bank_connectors.{self.institution_id}")

    @property
    @abstractmethod
    def institution_id(self) -> str:
        """Unique identifier for the financial institution"""
        pass

    @property
    @abstractmethod
    def institution_name(self) -> str:
        """Display name for the financial institution"""
        pass

    @property
    def supports_oauth(self) -> bool:
        """Whether this connector supports OAuth flow - override in subclass"""
        return True

    @property
    def supports_refresh(self) -> bool:
        """Whether this connector supports token refresh - override in subclass"""
        return True

    @abstractmethod
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get OAuth authorization URL"""
        pass

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> TokenInfo:
        """Exchange authorization code for tokens"""
        pass

    @abstractmethod
    def refresh_token(self, token_info: TokenInfo) -> TokenInfo:
        """Refresh an expired token"""
        pass

    @abstractmethod
    def get_accounts(self, token_info: TokenInfo) -> list[Account]:
        """Fetch accounts for the connected user"""
        pass

    @abstractmethod
    def get_transactions(
        self,
        token_info: TokenInfo,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Transaction]:
        """Fetch transactions for an account"""
        pass

    def disconnect(self, token_info: TokenInfo | None = None) -> bool:
        """Disconnect and revoke access - override for custom behavior"""
        self._logger.info(f"Disconnecting from {self.institution_name}")
        return True

    @property
    def config(self) -> ConnectorConfig:
        """Get connector configuration"""
        return self._config

    @config.setter
    def config(self, value: ConnectorConfig) -> None:
        """Set connector configuration"""
        self._config = value

    def _log(self, level: int, message: str, **kwargs) -> None:
        """Internal logging helper"""
        self._logger.log(level, message, **kwargs)