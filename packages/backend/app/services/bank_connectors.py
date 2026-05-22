from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from .expense_import import normalize_import_rows


class BankConnector(Protocol):
    """Interface implemented by pluggable bank integrations."""

    name: str

    def import_transactions(
        self,
        *,
        account_id: str,
        since: date | None = None,
        until: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return transaction-like rows from the provider."""

    def refresh_transactions(self, *, account_id: str) -> list[dict[str, Any]]:
        """Return the most recent provider rows for an account."""


@dataclass(frozen=True)
class BankTransaction:
    date: str
    amount: float
    description: str
    currency: str = "USD"
    category_id: int | None = None
    expense_type: str | None = None
    provider_transaction_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_import_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "date": self.date,
            "amount": self.amount,
            "description": self.description,
            "currency": self.currency,
            "category_id": self.category_id,
        }
        if self.expense_type:
            row["expense_type"] = self.expense_type
        if self.provider_transaction_id:
            row["provider_transaction_id"] = self.provider_transaction_id
        if self.metadata:
            row["metadata"] = dict(self.metadata)
        return row


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BankConnector] = {}

    def register(self, connector: BankConnector) -> None:
        key = _normalize_connector_name(connector.name)
        self._connectors[key] = connector

    def get(self, name: str) -> BankConnector:
        key = _normalize_connector_name(name)
        try:
            return self._connectors[key]
        except KeyError as exc:
            raise ValueError(f"unknown bank connector: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._connectors)


class MockBankConnector:
    name = "mock"

    def __init__(
        self,
        transactions: list[BankTransaction | dict[str, Any]] | None = None,
    ) -> None:
        self._transactions = transactions or [
            BankTransaction(
                date="2026-02-10",
                amount=-12.45,
                description="Mock Coffee",
                currency="USD",
                provider_transaction_id="mock_txn_1",
            ),
            BankTransaction(
                date="2026-02-11",
                amount=2500.00,
                description="Mock Payroll",
                currency="USD",
                expense_type="INCOME",
                provider_transaction_id="mock_txn_2",
            ),
        ]

    def import_transactions(
        self,
        *,
        account_id: str,
        since: date | None = None,
        until: date | None = None,
    ) -> list[dict[str, Any]]:
        _require_account_id(account_id)
        rows = [self._to_row(tx) for tx in self._transactions]
        return _filter_rows_by_date(rows, since=since, until=until)

    def refresh_transactions(self, *, account_id: str) -> list[dict[str, Any]]:
        _require_account_id(account_id)
        return [self._to_row(tx) for tx in self._transactions]

    @staticmethod
    def _to_row(tx: BankTransaction | dict[str, Any]) -> dict[str, Any]:
        if isinstance(tx, BankTransaction):
            return tx.to_import_row()
        return dict(tx)


def import_bank_transactions(
    *,
    connector_name: str,
    account_id: str,
    since: date | None = None,
    until: date | None = None,
    registry: ConnectorRegistry | None = None,
) -> list[dict[str, Any]]:
    connector = _registry(registry).get(connector_name)
    rows = connector.import_transactions(
        account_id=account_id,
        since=since,
        until=until,
    )
    return normalize_import_rows(rows)


def refresh_bank_transactions(
    *,
    connector_name: str,
    account_id: str,
    registry: ConnectorRegistry | None = None,
) -> list[dict[str, Any]]:
    connector = _registry(registry).get(connector_name)
    rows = connector.refresh_transactions(account_id=account_id)
    return normalize_import_rows(rows)


def default_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(MockBankConnector())
    return registry


def _registry(registry: ConnectorRegistry | None) -> ConnectorRegistry:
    return registry if registry is not None else default_registry()


def _normalize_connector_name(name: str) -> str:
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("connector name required")
    return key


def _require_account_id(account_id: str) -> None:
    if not (account_id or "").strip():
        raise ValueError("account_id required")


def _filter_rows_by_date(
    rows: list[dict[str, Any]],
    *,
    since: date | None,
    until: date | None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        raw_date = str(row.get("date") or "")
        try:
            row_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if since and row_date < since:
            continue
        if until and row_date > until:
            continue
        filtered.append(row)
    return filtered
