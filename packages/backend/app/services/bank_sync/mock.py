"""In-memory mock bank connector used for development and tests.

The mock connector accepts any non-empty ``api_key`` and exposes two
deterministic accounts. ``fetch_transactions`` returns a fixed list of
transactions which can be filtered by ``since``. Tests can override the
canned data by mutating :data:`MOCK_ACCOUNTS` or :data:`MOCK_TRANSACTIONS`
before calling the connector.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .base import BankAccountInfo, BankConnector, BankTransaction, ConnectorError
from .registry import register_connector


MOCK_ACCOUNTS: list[BankAccountInfo] = [
    BankAccountInfo(
        external_id="mock-checking-001",
        name="Mock Checking",
        account_type="checking",
        currency="USD",
    ),
    BankAccountInfo(
        external_id="mock-savings-002",
        name="Mock Savings",
        account_type="savings",
        currency="USD",
    ),
]


MOCK_TRANSACTIONS: dict[str, list[BankTransaction]] = {
    "mock-checking-001": [
        BankTransaction(
            external_id="mock-tx-1",
            date=date(2026, 2, 1),
            amount=12.50,
            description="Coffee Shop",
            currency="USD",
            expense_type="EXPENSE",
        ),
        BankTransaction(
            external_id="mock-tx-2",
            date=date(2026, 2, 5),
            amount=2500.00,
            description="Payroll Deposit",
            currency="USD",
            expense_type="INCOME",
        ),
        BankTransaction(
            external_id="mock-tx-3",
            date=date(2026, 2, 12),
            amount=42.00,
            description="Grocery Run",
            currency="USD",
            expense_type="EXPENSE",
        ),
    ],
    "mock-savings-002": [
        BankTransaction(
            external_id="mock-tx-s1",
            date=date(2026, 2, 3),
            amount=500.00,
            description="Transfer In",
            currency="USD",
            expense_type="INCOME",
        ),
    ],
}


@register_connector
class MockConnector(BankConnector):
    provider_name = "mock"
    display_name = "Mock Bank"
    required_credentials = ("api_key",)

    def connect(self, credentials: dict[str, Any]) -> list[BankAccountInfo]:
        api_key = (credentials or {}).get("api_key")
        if not api_key:
            raise ConnectorError("api_key is required")
        return list(MOCK_ACCOUNTS)

    def fetch_transactions(
        self,
        external_account_id: str,
        *,
        since: date | None = None,
    ) -> list[BankTransaction]:
        if external_account_id not in MOCK_TRANSACTIONS:
            raise ConnectorError(f"unknown account: {external_account_id}")
        txs = MOCK_TRANSACTIONS[external_account_id]
        if since is not None:
            txs = [t for t in txs if t.date >= since]
        return list(txs)
