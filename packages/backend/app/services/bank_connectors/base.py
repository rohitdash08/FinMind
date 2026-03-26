"""
Abstract base class and data models for bank connectors.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class TransactionType(str, Enum):
    """Type of financial transaction."""

    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
    FEE = "FEE"
    REFUND = "REFUND"


class AccountType(str, Enum):
    """Type of bank account."""

    CHECKING = "CHECKING"
    SAVINGS = "SAavings"
    CREDIT = "CREDIT"
    INVESTMENT = "INVESTMENT"
    LOAN = "LOAN"
    UNKNOWN = "UNKNOWN"


@dataclass
class Transaction:
    """
    Represents a single financial transaction from a bank account.

    All monetary amounts are stored as positive floats in the smallest
    currency unit (e.g., cents for USD). The `transaction_type` field
    indicates the direction of the flow from the account holder's
    perspective.
    """

    date: date
    """Date the transaction was posted."""

    amount: float
    """Absolute amount in smallest currency unit (e.g., cents)."""

    description: str
    """Human-readable transaction description."""

    transaction_type: TransactionType = TransactionType.EXPENSE
    """Direction of the transaction."""

    currency: str = "USD"
    """ISO 4217 currency code."""

    category: str | None = None
    """Bank-supplied or inferred category label."""

    merchant_name: str | None = None
    """Normalized merchant name, if identifiable."""

    transaction_id: str | None = None
    """Bank's unique transaction reference, if available."""

    pending: bool = False
    """Whether the transaction is still pending settlement."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Connector-specific extra data."""

    def to_expense_dict(self) -> dict[str, Any]:
        """Convert to the normalized expense dict used by FinMind's import pipeline."""
        expense_type = "EXPENSE"
        if self.transaction_type in (TransactionType.CREDIT, TransactionType.INCOME):
            expense_type = "INCOME"
        elif self.transaction_type == TransactionType.TRANSFER:
            expense_type = "EXPENSE"
        return {
            "date": self.date.isoformat(),
            "amount": abs(self.amount),
            "description": self.description[:500],
            "currency": self.currency,
            "expense_type": expense_type,
            "category_id": None,
            "transaction_id": self.transaction_id,
            "pending": self.pending,
            "metadata": self.metadata,
        }


@dataclass
class Account:
    """
    Represents a bank account linked via a connector.
    """

    account_id: str
    """Provider's unique account identifier."""

    account_name: str
    """Display name of the account (e.g., 'Checking ****1234')."""

    account_type: AccountType = AccountType.UNKNOWN
    """Type of account."""

    currency: str = "USD"
    """ISO 4217 currency code."""

    current_balance: float | None = None
    """Current available balance in smallest currency unit."""

    available_balance: float | None = None
    """Available balance (may differ from current_balance)."""

    institution_name: str | None = None
    """Name of the bank or financial institution."""

    mask: str | None = None
    """Last 4 digits of the account number (for display)."""

    is_active: bool = True
    """Whether the account is currently active."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Connector-specific extra data."""


@dataclass
class ConnectorAuthStatus:
    """Describes the current authentication state of a connector instance."""

    connected: bool = False
    """True if the connector has valid credentials and can make API calls."""

    user_id: str | None = None
    """Identifier of the connected bank user, if known."""

    institution_name: str | None = None
    """Name of the connected institution."""

    expires_at: datetime | None = None
    """When the current auth token expires, if applicable."""

    error_message: str | None = None
    """Error description if not connected."""


class ConnectorError(Exception):
    """Base exception raised by bank connectors."""

    pass


class AuthenticationError(ConnectorError):
    """Raised when credentials or OAuth tokens are invalid or expired."""

    pass


class RateLimitError(ConnectorError):
    """Raised when the connector hits an API rate limit."""

    pass


class AccountNotFoundError(ConnectorError):
    """Raised when a requested account does not exist or is not accessible."""

    pass


class BankConnector(ABC):
    """
    Abstract interface that every bank connector must implement.

    Connectors are stateful per-user instances. Store any required
    credentials or tokens in the `config` dict passed to ``__init__``.

    Thread-safety is the caller's responsibility; create a fresh connector
    instance per request or per background job when needed.
    """

    name: str = "unknown"
    """Unique identifier for this connector (e.g., 'chase', 'mock')."""

    display_name: str = "Unknown Bank"
    """Human-readable name shown in the UI."""

    supports_refresh: bool = True
    """Whether the connector can fetch new transactions without re-import."""

    supports_oauth: bool = False
    """Whether the connector uses OAuth 2.0 flow (vs. API key / credentials)."""

    website_url: str | None = None
    """Link to the bank's official website."""

    icon_url: str | None = None
    """URL of the bank's icon/logo."""

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the connector with user-specific configuration.

        Args:
            config: Dictionary containing connector-specific auth data.
                For OAuth connectors this typically includes ``access_token``
                and ``refresh_token``. For API-key connectors it may contain
                ``api_key``, ``client_id``, ``client_secret``, etc.
                The ``user_id`` key is always present and contains the
                FinMind user ID for this connection.
        """
        ...

    @abstractmethod
    def get_auth_status(self) -> ConnectorAuthStatus:
        """
        Verify credentials and return the current authentication status.

        Returns:
            ConnectorAuthStatus describing the current auth state.
        """
        ...

    @abstractmethod
    def list_accounts(self) -> list[Account]:
        """
        Return all accounts accessible with the current credentials.

        Returns:
            List of Account objects.

        Raises:
            AuthenticationError: If credentials are invalid or expired.
            ConnectorError: For other connector-specific errors.
        """
        ...

    @abstractmethod
    def get_transactions(
        self,
        account_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Transaction]:
        """
        Fetch transactions for the specified account.

        Args:
            account_id: The ``account_id`` from a previously returned Account.
            from_date: Start of the date range (inclusive). None = unlimited.
            to_date: End of the date range (inclusive). None = today.

        Returns:
            List of Transaction objects in chronological order (oldest first).

        Raises:
            AccountNotFoundError: If the account_id is not found.
            AuthenticationError: If credentials are invalid or expired.
            RateLimitError: If the connector's API rate limit is exceeded.
            ConnectorError: For other connector-specific errors.
        """
        ...

    def refresh(self, account_id: str) -> list[Transaction]:
        """
        Refresh transactions for the given account, returning only *new*
        transactions since the last import.

        The default implementation fetches transactions from the last
        known import date (stored in metadata) up to today. Connectors that
        have a native "delta" or "webhook" mechanism should override this.

        Args:
            account_id: The account to refresh.

        Returns:
            List of new Transaction objects added since last refresh.

        Raises:
            Same as ``get_transactions``.
        """
        from .. import expense_import

        last_refresh = self._get_last_refresh_date(account_id)
        return self.get_transactions(account_id, from_date=last_refresh)

    # -------------------------------------------------------------------------
    # Internal helpers — optional to override
    # -------------------------------------------------------------------------

    def _get_last_refresh_date(self, account_id: str) -> date | None:
        """Return the date of the most recently imported transaction, if known."""
        return None

    def normalize_transactions(
        self, transactions: list[Transaction]
    ) -> list[dict[str, Any]]:
        """
        Convert connector Transaction objects into the expense_import
        normalized row format used by the rest of the application.

        This hook lets individual connectors adjust the normalization
        (e.g., map bank categories to FinMind category IDs) before the
        data is committed to the database.
        """
        from .. import expense_import

        rows = [t.to_expense_dict() for t in transactions]
        return expense_import.normalize_import_rows(rows)
