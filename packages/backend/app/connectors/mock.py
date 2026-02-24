"""Mock bank connector for development and CI testing.

Generates realistic-looking Indian bank transactions (INR, UPI, NEFT,
IMPS, etc.) without any external dependencies.  The data is
deterministic for a given ``seed`` so tests stay reproducible.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .base import (
    AccountType,
    BankAccount,
    BankConnector,
    BankTransaction,
    SyncResult,
    SyncStatus,
    TransactionStatus,
)

logger = logging.getLogger("finmind.connectors.mock")

# Realistic Indian-style payees / descriptions
_PAYEES: list[tuple[str, str]] = [
    ("UPI-Swiggy-Food", "EXPENSE"),
    ("UPI-Zomato", "EXPENSE"),
    ("NEFT-RENT-APR", "EXPENSE"),
    ("UPI-Amazon Pay", "EXPENSE"),
    ("UPI-Flipkart", "EXPENSE"),
    ("IMPS-ElectricityBill", "EXPENSE"),
    ("UPI-JioCinema", "EXPENSE"),
    ("NEFT-SALARY-ACME", "INCOME"),
    ("UPI-PhonePe-Refund", "INCOME"),
    ("IMPS-FreelancePay", "INCOME"),
    ("ATM-CASH-WITHDRAWAL", "EXPENSE"),
    ("UPI-BigBasket", "EXPENSE"),
    ("UPI-Uber", "EXPENSE"),
    ("NEFT-MutualFund-SIP", "EXPENSE"),
    ("UPI-Ola", "EXPENSE"),
]

_MOCK_ACCOUNTS: list[dict[str, Any]] = [
    {
        "external_id": "mock-sav-001",
        "name": "HDFC Savings ****1234",
        "account_type": AccountType.SAVINGS,
        "balance": Decimal("84367.50"),
        "currency": "INR",
        "masked_number": "XXXX1234",
    },
    {
        "external_id": "mock-cc-001",
        "name": "ICICI Credit Card ****5678",
        "account_type": AccountType.CREDIT_CARD,
        "balance": Decimal("-12450.00"),
        "currency": "INR",
        "masked_number": "XXXX5678",
    },
]


class MockBankConnector(BankConnector):
    """Generates deterministic mock data.  Useful for local dev + CI.

    Config keys:
        - ``seed`` (str): seed for deterministic generation (default "mock").
        - ``transaction_count`` (int): how many transactions to generate
          per import call (default 30).
        - ``fail_auth`` (bool): if True, ``authenticate`` always fails.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._seed: str = str(cfg.get("seed", "mock"))
        self._tx_count: int = int(cfg.get("transaction_count", 30))
        self._fail_auth: bool = bool(cfg.get("fail_auth", False))
        self._authenticated: bool = False

    # ------------------------------------------------------------------
    # BankConnector implementation
    # ------------------------------------------------------------------

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        if self._fail_auth:
            logger.info("MockBankConnector: auth forced to fail")
            return False
        self._authenticated = True
        logger.info("MockBankConnector: authenticated")
        return True

    def get_accounts(self) -> list[BankAccount]:
        self._require_auth()
        return [BankAccount(**acct) for acct in _MOCK_ACCOUNTS]

    def import_transactions(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> SyncResult:
        self._require_auth()
        txns = self._generate(account_id, start_date, end_date)
        cursor = end_date.isoformat()
        logger.info(
            "MockBankConnector: imported %d txns for %s (%s – %s)",
            len(txns),
            account_id,
            start_date,
            end_date,
        )
        return SyncResult(
            status=SyncStatus.SUCCESS,
            transactions=txns,
            cursor=cursor,
        )

    def refresh(
        self,
        account_id: str,
        cursor: str | None = None,
    ) -> SyncResult:
        self._require_auth()
        if cursor:
            start = date.fromisoformat(cursor)
        else:
            start = date.today() - timedelta(days=30)
        end = date.today()
        txns = self._generate(account_id, start, end)
        logger.info(
            "MockBankConnector: refreshed %d txns for %s (cursor=%s)",
            len(txns),
            account_id,
            cursor,
        )
        return SyncResult(
            status=SyncStatus.SUCCESS,
            transactions=txns,
            cursor=end.isoformat(),
        )

    def disconnect(self) -> None:
        self._authenticated = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_auth(self) -> None:
        if not self._authenticated:
            raise RuntimeError("MockBankConnector: not authenticated")

    def _generate(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[BankTransaction]:
        """Build a deterministic list of mock transactions."""
        days = max(1, (end_date - start_date).days)
        count = min(self._tx_count, days * 3)
        txns: list[BankTransaction] = []
        for i in range(count):
            digest = hashlib.md5(  # noqa: S324  # nosec B324
                f"{self._seed}:{account_id}:{i}".encode(),
                usedforsecurity=False,
            ).hexdigest()
            idx = int(digest[:4], 16) % len(_PAYEES)
            payee, txn_type = _PAYEES[idx]

            day_offset = int(digest[4:8], 16) % days
            txn_date = start_date + timedelta(days=day_offset)

            raw_amount = (int(digest[8:12], 16) % 9000 + 100) / 100
            amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
            if txn_type == "INCOME":
                amount = amount * 10  # incomes tend to be larger

            txns.append(
                BankTransaction(
                    external_id=f"mock-tx-{digest[:12]}",
                    date=txn_date,
                    amount=amount,
                    description=payee,
                    currency="INR",
                    category_hint=txn_type,
                    status=TransactionStatus.POSTED,
                    reference=f"REF{digest[:8].upper()}",
                )
            )
        txns.sort(key=lambda t: t.date)
        return txns
