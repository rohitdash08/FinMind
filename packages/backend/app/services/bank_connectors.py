from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any


class BankConnector(ABC):
    """Contract for pluggable bank data providers."""

    name: str

    @abstractmethod
    def import_transactions(
        self,
        *,
        user_id: int,
        credentials: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a full import payload from provider."""

    @abstractmethod
    def refresh_transactions(
        self,
        *,
        user_id: int,
        credentials: Mapping[str, Any] | None = None,
        last_sync_at: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch only new/updated transactions since the prior sync marker."""


class MockBankConnector(BankConnector):
    """Deterministic test connector for local/dev and integration tests."""

    name = "mock"

    def import_transactions(
        self,
        *,
        user_id: int,
        credentials: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = user_id, credentials
        return [
            {
                "date": "2026-02-14",
                "amount": "32.10",
                "description": "Mock Grocery Store",
                "currency": "USD",
            },
            {
                "date": "2026-02-15",
                "amount": "1200.00",
                "description": "Mock Payroll",
                "currency": "USD",
                "expense_type": "INCOME",
            },
        ]

    def refresh_transactions(
        self,
        *,
        user_id: int,
        credentials: Mapping[str, Any] | None = None,
        last_sync_at: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = user_id, credentials
        sync_date = date.today() - timedelta(days=1)
        if last_sync_at:
            try:
                sync_date = date.fromisoformat(last_sync_at)
            except ValueError:
                sync_date = date.today() - timedelta(days=1)

        return [
            {
                "date": (sync_date + timedelta(days=1)).isoformat(),
                "amount": "19.99",
                "description": "Mock Streaming Subscription",
                "currency": "USD",
            }
        ]


def get_connector_registry() -> dict[str, BankConnector]:
    return {MockBankConnector.name: MockBankConnector()}


def get_connector(name: str, registry: Mapping[str, BankConnector] | None = None) -> BankConnector | None:
    connectors = registry or get_connector_registry()
    return connectors.get((name or "").strip().lower())
