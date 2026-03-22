"""Mock bank connector for testing and local development."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from .base import BankAccount, BankConnector, BankTransaction, ImportResult

_MOCK_ACCOUNTS = [
    BankAccount(
        account_id="mock-savings-001",
        account_name="Mock Savings Account",
        account_type="SAVINGS",
        balance=50000.0,
        currency="INR",
        institution_name="Mock Bank",
        masked_account_number="XXXX1234",
    ),
    BankAccount(
        account_id="mock-current-002",
        account_name="Mock Current Account",
        account_type="CURRENT",
        balance=120000.0,
        currency="INR",
        institution_name="Mock Bank",
        masked_account_number="XXXX5678",
    ),
]

_MOCK_TRANSACTIONS_TEMPLATE = [
    {
        "description": "Salary Credit",
        "amount": 80000.0,
        "transaction_type": "CREDIT",
        "category": "INCOME",
        "offset_days": 1,
    },
    {
        "description": "Grocery Store",
        "amount": 2500.0,
        "transaction_type": "DEBIT",
        "category": "FOOD",
        "offset_days": 3,
    },
    {
        "description": "Electricity Bill",
        "amount": 1800.0,
        "transaction_type": "DEBIT",
        "category": "UTILITIES",
        "offset_days": 5,
    },
    {
        "description": "Online Transfer",
        "amount": 5000.0,
        "transaction_type": "DEBIT",
        "category": "TRANSFER",
        "offset_days": 7,
    },
    {
        "description": "ATM Withdrawal",
        "amount": 3000.0,
        "transaction_type": "DEBIT",
        "category": "CASH",
        "offset_days": 10,
    },
    {
        "description": "Mobile Recharge",
        "amount": 299.0,
        "transaction_type": "DEBIT",
        "category": "TELECOM",
        "offset_days": 12,
    },
    {
        "description": "Restaurant",
        "amount": 750.0,
        "transaction_type": "DEBIT",
        "category": "FOOD",
        "offset_days": 14,
    },
    {
        "description": "Interest Credit",
        "amount": 350.0,
        "transaction_type": "CREDIT",
        "category": "INCOME",
        "offset_days": 15,
    },
]


def _make_transaction(
    account_id: str,
    tmpl: dict[str, Any],
    base_date: date,
    idx: int,
) -> BankTransaction:
    tx_date = base_date + timedelta(days=tmpl["offset_days"])
    raw = f"{account_id}:{tmpl['description']}:{tx_date.isoformat()}:{idx}"
    tid = "mock-" + hashlib.md5(raw.encode()).hexdigest()[:12]
    return BankTransaction(
        transaction_id=tid,
        account_id=account_id,
        amount=tmpl["amount"],
        currency="INR",
        description=tmpl["description"],
        transaction_date=tx_date,
        transaction_type=tmpl["transaction_type"],
        category=tmpl.get("category"),
        reference=f"REF{tid.upper()}",
    )


def _generate_transactions(
    account_id: str,
    from_date: date,
    to_date: date,
) -> list[BankTransaction]:
    """Generate deterministic fake transactions within the date window."""
    transactions: list[BankTransaction] = []
    cursor = from_date.replace(day=1)
    idx = 0
    while cursor <= to_date:
        for tmpl in _MOCK_TRANSACTIONS_TEMPLATE:
            tx = _make_transaction(account_id, tmpl, cursor, idx)
            if from_date <= tx.transaction_date <= to_date:
                transactions.append(tx)
            idx += 1
        # Move to next month
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    transactions.sort(key=lambda t: t.transaction_date)
    return transactions


class MockBankConnector(BankConnector):
    """In-memory mock connector useful for development and testing.

    This connector does not contact any real banking service.  All returned
    accounts and transactions are generated deterministically so tests remain
    reproducible.

    Credentials accepted (all optional):
        - ``user``: any string – ignored, present for interface compliance.
    """

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def display_name(self) -> str:
        return "Mock Bank (demo)"

    def fetch_accounts(self, credentials: dict[str, Any]) -> list[BankAccount]:  # noqa: ARG002
        return list(_MOCK_ACCOUNTS)

    def import_transactions(
        self,
        credentials: dict[str, Any],  # noqa: ARG002
        account_id: str,
        from_date: date,
        to_date: date,
        cursor: str | None = None,
    ) -> ImportResult:
        txns = _generate_transactions(account_id, from_date, to_date)
        # Cursor encodes the last transaction_date seen (ISO format)
        if cursor:
            try:
                last_seen = date.fromisoformat(cursor)
                txns = [t for t in txns if t.transaction_date > last_seen]
            except ValueError:
                pass
        new_cursor = txns[-1].transaction_date.isoformat() if txns else cursor
        return ImportResult(transactions=txns, cursor=new_cursor, has_more=False)

    def refresh(
        self,
        credentials: dict[str, Any],
        account_id: str,
        cursor: str | None = None,
    ) -> ImportResult:
        to_date = date.today()
        if cursor:
            try:
                from_date = date.fromisoformat(cursor) + timedelta(days=1)
            except ValueError:
                from_date = to_date - timedelta(days=30)
        else:
            from_date = to_date - timedelta(days=30)
        return self.import_transactions(
            credentials, account_id, from_date, to_date, cursor=None
        )
