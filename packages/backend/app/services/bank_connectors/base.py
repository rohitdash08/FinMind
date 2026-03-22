"""Bank connector interface definition."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class BankAccount:
    """Represents a bank account returned by a connector."""

    account_id: str
    account_name: str
    account_type: str
    balance: float
    currency: str
    institution_name: str
    masked_account_number: str | None = None


@dataclass
class BankTransaction:
    """Represents a single bank transaction returned by a connector."""

    transaction_id: str
    account_id: str
    amount: float
    currency: str
    description: str
    transaction_date: date
    transaction_type: str  # DEBIT or CREDIT
    category: str | None = None
    reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportResult:
    """Result of an import or refresh operation."""

    transactions: list[BankTransaction]
    cursor: str | None = None  # opaque cursor for incremental sync
    has_more: bool = False


class BankConnector(ABC):
    """Abstract base class for all bank connector implementations.

    Subclasses must implement :meth:`fetch_accounts`, :meth:`import_transactions`,
    and :meth:`refresh` along with the :attr:`provider_id` and
    :attr:`display_name` properties.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique slug that identifies this connector (e.g. ``mock``, ``finvu``)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""
        ...

    @abstractmethod
    def fetch_accounts(self, credentials: dict[str, Any]) -> list[BankAccount]:
        """Return the list of accounts accessible via *credentials*.

        Args:
            credentials: Provider-specific auth data (tokens, API keys, etc.).

        Returns:
            List of :class:`BankAccount` objects.
        """
        ...

    @abstractmethod
    def import_transactions(
        self,
        credentials: dict[str, Any],
        account_id: str,
        from_date: date,
        to_date: date,
        cursor: str | None = None,
    ) -> ImportResult:
        """Perform a full or date-ranged import of transactions.

        Args:
            credentials: Provider-specific auth data.
            account_id: The account to fetch from.
            from_date: Inclusive start date for the fetch window.
            to_date: Inclusive end date for the fetch window.
            cursor: Optional opaque cursor returned by a previous call for
                pagination.

        Returns:
            :class:`ImportResult` containing transactions and a next cursor.
        """
        ...

    @abstractmethod
    def refresh(
        self,
        credentials: dict[str, Any],
        account_id: str,
        cursor: str | None = None,
    ) -> ImportResult:
        """Incrementally sync new transactions since the last cursor.

        Implementations should fetch only transactions that occurred after the
        position described by *cursor*.  When *cursor* is ``None`` the
        connector should return the most recent page of transactions.

        Args:
            credentials: Provider-specific auth data.
            account_id: The account to sync.
            cursor: Opaque cursor from the previous sync (or ``None``).

        Returns:
            :class:`ImportResult` with new transactions and an updated cursor.
        """
        ...
