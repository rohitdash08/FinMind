"""
Mock bank connector for development and testing.

The ``MockBankConnector`` simulates a real bank connection without making
any external API calls. It generates deterministic transaction data that
can be used to exercise the full import pipeline.

Use in development::

    connector = MockBankConnector({"user_id": "123", "mode": "default"})
    status = connector.get_auth_status()
    accounts = connector.list_accounts()
    transactions = connector.get_transactions(accounts[0].account_id)

For testing, set ``mode="empty"`` to return accounts with no transactions,
or ``mode="error"`` to exercise error handling paths.
"""
from __future__ import annotations

import random
import hashlib
from datetime import date, timedelta
from typing import Any

from .base import (
    Account,
    AccountType,
    BankConnector,
    ConnectorAuthStatus,
    ConnectorError,
    Transaction,
    TransactionType,
)


class MockConnectorError(ConnectorError):
    """Simulated error raised by MockBankConnector in error mode."""

    pass


class MockBankConnector(BankConnector):
    """
    Mock connector that generates realistic-looking fake transaction data.

    Configuration keys (passed to ``__init__`` via the ``config`` dict):

    - ``user_id`` (str): FinMind user ID this connection belongs to.
    - ``mode`` (str): One of ``default``, ``empty``, ``error``. Default produces
      a full set of accounts and transactions.
    - ``seed`` (int): Random seed for reproducible transaction generation.
      Omit or pass ``None`` for non-deterministic data.
    - ``account_count`` (int): Number of mock accounts to simulate (default 2).
    - ``transaction_days`` (int): Number of days of history to generate
      (default 30, max 365).
    """

    name = "mock"
    display_name = "Mock Bank (Dev)"
    supports_refresh = True
    supports_oauth = False
    website_url = "https://example.com/mock-bank"
    icon_url = None

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.user_id = str(config.get("user_id", ""))
        self.mode = str(config.get("mode", "default")).lower()
        self.seed = config.get("seed")
        self._rng = random.Random(self.seed)

        # Configuration for data generation
        self._account_count = int(config.get("account_count", 2))
        self._transaction_days = min(int(config.get("transaction_days", 30)), 365)

        # Pre-generate deterministic account IDs based on user_id + seed
        self._accounts = self._generate_accounts() if self.mode not in ("error", "empty") else []

    # -------------------------------------------------------------------------
    # BankConnector interface
    # -------------------------------------------------------------------------

    def get_auth_status(self) -> ConnectorAuthStatus:
        if self.mode == "error":
            return ConnectorAuthStatus(
                connected=False,
                error_message="Simulated authentication failure (mock connector in error mode).",
            )
        return ConnectorAuthStatus(
            connected=True,
            user_id=self.user_id,
            institution_name=self.display_name,
        )

    def list_accounts(self) -> list[Account]:
        if self.mode == "error":
            raise MockConnectorError(
                "Cannot list accounts: mock connector is in error mode."
            )
        if self.mode == "empty":
            return []
        return self._accounts

    def get_transactions(
        self,
        account_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Transaction]:
        if self.mode == "error":
            raise MockConnectorError(
                "Cannot fetch transactions: mock connector is in error mode."
            )
        if self.mode == "empty":
            return []

        account = next((a for a in self._accounts if a.account_id == account_id), None)
        if account is None:
            raise ConnectorError(f"Account not found: {account_id}")

        if self.mode == "empty":
            return []

        to_date = to_date or date.today()
        from_date = from_date or (to_date - timedelta(days=self._transaction_days))

        return self._generate_transactions(account, from_date, to_date)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _generate_accounts(self) -> list[Account]:
        rng = self._rng
        accounts = []
        account_templates = [
            {
                "account_name": "Checking Account",
                "account_type": AccountType.CHECKING,
                "mask": f"{rng.randint(1000, 9999):04d}",
                "current_balance": round(rng.uniform(1000, 50000), 2),
                "currency": "USD",
            },
            {
                "account_name": "Savings Account",
                "account_type": AccountType.SAVINGS,
                "mask": f"{rng.randint(1000, 9999):04d}",
                "current_balance": round(rng.uniform(5000, 100000), 2),
                "currency": "USD",
            },
        ]

        if self._account_count > 2:
            extra_templates = [
                {
                    "account_name": "Credit Card",
                    "account_type": AccountType.CREDIT,
                    "mask": f"{rng.randint(1000, 9999):04d}",
                    "current_balance": round(rng.uniform(500, 5000), 2),
                    "currency": "USD",
                },
            ]
            account_templates.extend(extra_templates[: self._account_count - 2])

        for i, tmpl in enumerate(account_templates[: self._account_count]):
            account_id = self._make_account_id(self.user_id, str(i), tmpl["mask"])
            accounts.append(
                Account(
                    account_id=account_id,
                    account_name=f"{tmpl['account_name']} ****{tmpl['mask']}",
                    account_type=tmpl["account_type"],
                    currency=tmpl["currency"],
                    current_balance=tmpl["current_balance"],
                    available_balance=round(tmpl["current_balance"] * rng.uniform(0.9, 1.0), 2),
                    institution_name=self.display_name,
                    mask=tmpl["mask"],
                    is_active=True,
                )
            )
        return accounts

    def _generate_transactions(
        self, account: Account, from_date: date, to_date: date
    ) -> list[Transaction]:
        rng = self._rng
        transactions = []
        delta = to_date - from_date
        num_tx = min(delta.days, self._transaction_days * 2)  # ~2 tx/day max

        merchant_templates = [
            ("Grocery Store", "EXPENSE", 20, 200),
            ("Amazon", "EXPENSE", 10, 500),
            ("Netflix", "EXPENSE", 15, 15),
            ("Spotify", "EXPENSE", 10, 10),
            ("Starbucks", "EXPENSE", 5, 20),
            ("Gas Station", "EXPENSE", 30, 80),
            ("Restaurant", "EXPENSE", 20, 150),
            ("Pharmacy", "EXPENSE", 10, 100),
            ("Uber", "EXPENSE", 10, 50),
            ("Electric Bill", "EXPENSE", 50, 200),
            ("Internet Bill", "EXPENSE", 40, 80),
            ("Salary Deposit", "INCOME", 2000, 5000),
            ("Freelance Payment", "INCOME", 200, 2000),
            ("Dividend", "INCOME", 10, 100),
            ("ATM Withdrawal", "EXPENSE", 20, 200),
            ("Online Shopping", "EXPENSE", 20, 300),
            ("Insurance", "EXPENSE", 100, 300),
            ("Rent Payment", "EXPENSE", 1000, 2000),
            ("Transfer to Savings", "TRANSFER", 100, 500),
            ("Interest Credit", "CREDIT", 1, 20),
        ]

        # Generate a deterministic set of dates
        all_dates = [from_date + timedelta(days=i) for i in range(delta.days + 1)]
        rng.shuffle(all_dates)
        selected_dates = sorted(all_dates[:num_tx])

        for i, tx_date in enumerate(selected_dates):
            merchant, tx_type_str, min_amt, max_amt = rng.choice(merchant_templates)
            amount = round(rng.uniform(min_amt, max_amt), 2)
            tx_type = TransactionType(tx_type_str)

            # Use a deterministic but unique transaction ID
            tx_id = hashlib.sha256(
                f"{self.user_id}:{account.account_id}:{tx_date.isoformat()}:{i}".encode()
            ).hexdigest()[:16]

            transactions.append(
                Transaction(
                    date=tx_date,
                    amount=amount,
                    description=merchant,
                    transaction_type=tx_type,
                    currency=account.currency,
                    merchant_name=merchant,
                    transaction_id=tx_id,
                    pending=tx_date == date.today() and rng.random() < 0.1,
                )
            )

        return sorted(transactions, key=lambda t: t.date)

    @staticmethod
    def _make_account_id(user_id: str, index: str, mask: str) -> str:
        raw = f"{user_id}:mock:{index}:{mask}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
