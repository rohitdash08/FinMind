from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


class ConnectorError(Exception):
    """Raised when a connector cannot complete an operation."""


@dataclass
class BankAccountInfo:
    """Account metadata returned by a connector during ``connect``."""

    external_id: str
    name: str
    account_type: str | None = None
    currency: str = "USD"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BankTransaction:
    """A single transaction returned by ``fetch_transactions``.

    ``external_id`` should be stable across refreshes so the caller can
    deduplicate. ``amount`` is always positive; ``expense_type`` is one of
    ``"EXPENSE"`` or ``"INCOME"``.
    """

    external_id: str
    date: date
    amount: float
    description: str
    currency: str = "USD"
    expense_type: str = "EXPENSE"

    def to_import_row(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "date": self.date.isoformat(),
            "amount": float(self.amount),
            "description": self.description,
            "currency": self.currency,
            "expense_type": self.expense_type,
        }


class BankConnector(ABC):
    """Interface every bank connector must implement.

    Subclasses must define ``provider_name`` and ``display_name`` and
    implement ``connect`` and ``fetch_transactions``.
    """

    provider_name: str = ""
    display_name: str = ""
    required_credentials: tuple[str, ...] = ()

    @abstractmethod
    def connect(self, credentials: dict[str, Any]) -> list[BankAccountInfo]:
        """Validate credentials and return the accounts available to link."""

    @abstractmethod
    def fetch_transactions(
        self,
        external_account_id: str,
        *,
        since: date | None = None,
    ) -> list[BankTransaction]:
        """Return transactions for an account.

        ``since`` is an inclusive lower bound on the transaction date. When
        ``None`` the connector should return its full available history,
        which is what ``import`` uses for the initial pull. ``refresh`` will
        pass the account's ``last_synced_at`` date.
        """
