from __future__ import annotations

from .base import BankConnector
from .models import BankAccount, BankTransaction


class MockBankConnector(BankConnector):
    provider_id = "mock"

    def __init__(self) -> None:
        self._connected = False
        self._page_size = 5
        self._accounts = [
            BankAccount(
                id="acc_hdfc_001",
                name="HDFC Savings",
                balance=245000.42,
                currency="INR",
            ),
            BankAccount(
                id="acc_icici_001",
                name="ICICI Salary",
                balance=98750.10,
                currency="INR",
            ),
        ]
        self._historical_transactions = [
            BankTransaction(
                "txn_0001",
                "acc_hdfc_001",
                -1250.0,
                "Swiggy order",
                "2026-02-01T13:30:00Z",
            ),
            BankTransaction(
                "txn_0002",
                "acc_hdfc_001",
                -5000.0,
                "Electricity bill",
                "2026-02-02T07:15:00Z",
            ),
            BankTransaction(
                "txn_0003",
                "acc_hdfc_001",
                75000.0,
                "Freelance payment",
                "2026-02-03T09:00:00Z",
            ),
            BankTransaction(
                "txn_0004",
                "acc_icici_001",
                -899.0,
                "UPI grocery",
                "2026-02-03T18:00:00Z",
            ),
            BankTransaction(
                "txn_0005",
                "acc_icici_001",
                -1499.0,
                "Mobile recharge",
                "2026-02-04T10:20:00Z",
            ),
            BankTransaction(
                "txn_0006",
                "acc_icici_001",
                120000.0,
                "Salary credit",
                "2026-02-05T05:45:00Z",
            ),
            BankTransaction(
                "txn_0007",
                "acc_hdfc_001",
                -3500.0,
                "Fuel expense",
                "2026-02-06T08:15:00Z",
            ),
            BankTransaction(
                "txn_0008",
                "acc_hdfc_001",
                -22000.0,
                "Rent transfer",
                "2026-02-07T03:30:00Z",
            ),
            BankTransaction(
                "txn_0009",
                "acc_icici_001",
                -299.0,
                "OTT subscription",
                "2026-02-08T15:00:00Z",
            ),
            BankTransaction(
                "txn_0010", "acc_icici_001", -760.0, "Cab ride", "2026-02-09T12:10:00Z"
            ),
        ]
        self._new_transactions = [
            BankTransaction(
                "txn_0011",
                "acc_hdfc_001",
                3000.0,
                "Merchant refund",
                "2026-02-10T11:00:00Z",
            ),
            BankTransaction(
                "txn_0012",
                "acc_hdfc_001",
                -125.0,
                "Coffee shop",
                "2026-02-11T17:20:00Z",
            ),
            BankTransaction(
                "txn_0013",
                "acc_icici_001",
                -6400.0,
                "Insurance premium",
                "2026-02-12T10:05:00Z",
            ),
        ]

    def connect(self, config: dict) -> None:
        page_size = config.get("page_size", self._page_size)
        if not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("Invalid page_size for MockBankConnector")
        self._page_size = page_size
        self._connected = True

    def import_accounts(self) -> list:
        self._ensure_connected()
        return [account.to_dict() for account in self._accounts]

    def import_transactions(self, cursor=None) -> tuple[list, str | None]:
        self._ensure_connected()
        full_stream = self._historical_transactions + self._new_transactions
        return self._paginate(full_stream, cursor)

    def refresh(self, cursor=None) -> tuple[list, str | None]:
        self._ensure_connected()
        start_offset = self._parse_cursor(cursor)
        historical_size = len(self._historical_transactions)

        # Refresh should only return transactions newer than initial historical import.
        refresh_start = max(start_offset, historical_size)
        full_stream = self._historical_transactions + self._new_transactions
        page = full_stream[refresh_start : refresh_start + self._page_size]
        next_offset = refresh_start + len(page)
        next_cursor = str(next_offset) if next_offset < len(full_stream) else None

        return [tx.to_dict() for tx in page], next_cursor

    def disconnect(self) -> None:
        self._connected = False

    def _paginate(
        self, transactions: list[BankTransaction], cursor=None
    ) -> tuple[list, str | None]:
        offset = self._parse_cursor(cursor)
        page = transactions[offset : offset + self._page_size]
        next_offset = offset + len(page)
        next_cursor = str(next_offset) if next_offset < len(transactions) else None
        return [tx.to_dict() for tx in page], next_cursor

    @staticmethod
    def _parse_cursor(cursor) -> int:
        if cursor in (None, ""):
            return 0
        try:
            parsed = int(cursor)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid cursor for MockBankConnector") from exc
        if parsed < 0:
            raise ValueError("Invalid cursor for MockBankConnector")
        return parsed

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("MockBankConnector is not connected")
