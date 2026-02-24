"""Bank Sync Connector Architecture — pluggable interface and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Standardised data types returned by all connectors
# ---------------------------------------------------------------------------


@dataclass
class BankAccount:
    """A single bank account discovered via the provider."""

    account_id: str
    label: str  # e.g. "HDFC Savings ****1234"
    type: str = "savings"  # savings / current / credit
    currency: str = "INR"
    meta: dict = field(default_factory=dict)


@dataclass
class Transaction:
    """A normalised bank transaction."""

    txn_id: str  # provider-specific unique id
    date: str  # ISO YYYY-MM-DD
    amount: float
    description: str
    currency: str = "INR"
    expense_type: str = "EXPENSE"  # EXPENSE / INCOME
    category_hint: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    """Returned by fetch / refresh to summarise the batch."""

    transactions: list[Transaction]
    cursor: str | None = None  # opaque cursor for incremental refresh
    has_more: bool = False


# ---------------------------------------------------------------------------
# Abstract connector interface
# ---------------------------------------------------------------------------


class BankConnector(ABC):
    """Every bank provider must implement this interface."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier, e.g. ``setu_aa``, ``mock``."""

    # -- consent / auth flow --------------------------------------------------

    @abstractmethod
    def create_consent(self, user_id: int, **kwargs: Any) -> dict:
        """Start the consent/auth flow.

        Returns a dict with at least ``consent_handle`` and optionally a
        ``redirect_url`` the frontend should open.
        """

    @abstractmethod
    def check_consent_status(self, consent_handle: str, **kwargs: Any) -> str:
        """Return consent status: ``pending``, ``approved``, ``rejected``."""

    # -- data fetching --------------------------------------------------------

    @abstractmethod
    def fetch_accounts(self, consent_handle: str, **kwargs: Any) -> list[BankAccount]:
        """Return accounts available under the given consent."""

    @abstractmethod
    def fetch_transactions(
        self,
        consent_handle: str,
        account_id: str,
        from_date: date,
        to_date: date,
        **kwargs: Any,
    ) -> SyncResult:
        """Full fetch of transactions for a date range."""

    @abstractmethod
    def refresh_transactions(
        self,
        consent_handle: str,
        account_id: str,
        cursor: str | None,
        **kwargs: Any,
    ) -> SyncResult:
        """Incremental fetch since the last cursor."""


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------

_registry: dict[str, type[BankConnector]] = {}


def register_connector(cls: type[BankConnector]) -> type[BankConnector]:
    """Class decorator — registers a connector by its ``provider_name``."""
    instance = cls()
    _registry[instance.provider_name] = cls
    return cls


def get_connector(provider: str) -> BankConnector:
    """Instantiate and return a connector by provider name."""
    cls = _registry.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown provider '{provider}'. " f"Available: {list(_registry.keys())}"
        )
    return cls()


def list_providers() -> list[str]:
    """Return all registered provider names."""
    return list(_registry.keys())
