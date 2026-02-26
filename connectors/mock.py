"""Mock bank connector with realistic fake data for testing."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from connectors.base import BankConnector, ConnectorError
from models.transaction import (
    Account, AccountType, Balance, Currency, Transaction,
    TransactionStatus, TransactionType,
)

_MERCHANTS = [
    ("Whole Foods Market", "Groceries", TransactionType.DEBIT),
    ("Amazon.com", "Shopping", TransactionType.DEBIT),
    ("Netflix", "Entertainment", TransactionType.DEBIT),
    ("Spotify", "Entertainment", TransactionType.DEBIT),
    ("Shell Gas Station", "Transportation", TransactionType.DEBIT),
    ("Starbucks", "Food & Drink", TransactionType.DEBIT),
    ("Target", "Shopping", TransactionType.DEBIT),
    ("Uber", "Transportation", TransactionType.DEBIT),
    ("Electric Company", "Utilities", TransactionType.DEBIT),
    ("City Water Dept", "Utilities", TransactionType.DEBIT),
    ("Employer Direct Deposit", "Income", TransactionType.CREDIT),
    ("Venmo Transfer", "Transfer", TransactionType.TRANSFER),
    ("ATM Withdrawal", "Cash", TransactionType.DEBIT),
    ("Interest Payment", "Interest", TransactionType.INTEREST),
    ("Monthly Service Fee", "Fees", TransactionType.FEE),
]


class MockConnector(BankConnector):
    """Mock connector that generates realistic fake banking data.

    Useful for testing, development, and demo purposes. Generates
    deterministic data based on the connector_id seed.
    """

    def __init__(self, connector_id: str = "mock-1", config: Optional[dict] = None):
        super().__init__(connector_id, config)
        seed = int(hashlib.md5(connector_id.encode()).hexdigest()[:8], 16)
        self._rng = random.Random(seed)
        self._accounts: Dict[str, Account] = {}
        self._balances: Dict[str, Balance] = {}
        self._last_refresh: Optional[datetime] = None

    @property
    def name(self) -> str:
        return "Mock Bank"

    @property
    def connector_type(self) -> str:
        return "mock"

    def connect(self) -> None:
        self._logger.info("Connecting to Mock Bank...")
        self._accounts = self._generate_accounts()
        self._balances = self._generate_balances()
        self._connected = True
        self._logger.info("Connected. %d accounts loaded.", len(self._accounts))

    def disconnect(self) -> None:
        self._logger.info("Disconnecting from Mock Bank.")
        self._connected = False
        self._accounts.clear()
        self._balances.clear()
        self._last_refresh = None

    def get_accounts(self) -> List[Account]:
        self._ensure_connected()
        return list(self._accounts.values())

    def get_balance(self, account_id: str) -> Balance:
        self._ensure_connected()
        if account_id not in self._balances:
            raise ConnectorError(f"Account {account_id!r} not found.")
        return self._balances[account_id]

    def import_transactions(
        self, start_date: datetime, end_date: datetime, account_id: Optional[str] = None
    ) -> List[Transaction]:
        self._ensure_connected()
        accounts = [account_id] if account_id else list(self._accounts.keys())
        transactions: List[Transaction] = []
        for aid in accounts:
            if aid not in self._accounts:
                raise ConnectorError(f"Account {aid!r} not found.")
            transactions.extend(self._generate_transactions(aid, start_date, end_date))
        self._last_refresh = end_date
        return sorted(transactions, key=lambda t: t.date, reverse=True)

    def refresh(self) -> List[Transaction]:
        self._ensure_connected()
        start = self._last_refresh or (datetime.utcnow() - timedelta(days=1))
        end = datetime.utcnow()
        return self.import_transactions(start, end)

    # -- internal generators --

    def _generate_accounts(self) -> Dict[str, Account]:
        specs = [
            (f"{self.connector_id}-chk", "Primary Checking", AccountType.CHECKING, "4521"),
            (f"{self.connector_id}-sav", "High-Yield Savings", AccountType.SAVINGS, "7832"),
            (f"{self.connector_id}-cc", "Rewards Credit Card", AccountType.CREDIT, "1099"),
        ]
        return {
            aid: Account(account_id=aid, name=name, account_type=atype,
                         mask=mask, institution_name="Mock Bank")
            for aid, name, atype, mask in specs
        }

    def _generate_balances(self) -> Dict[str, Balance]:
        out: Dict[str, Balance] = {}
        for aid, acct in self._accounts.items():
            if acct.account_type == AccountType.CHECKING:
                cur = round(self._rng.uniform(1000, 15000), 2)
                out[aid] = Balance(account_id=aid, current=cur, available=cur - 50)
            elif acct.account_type == AccountType.SAVINGS:
                cur = round(self._rng.uniform(5000, 50000), 2)
                out[aid] = Balance(account_id=aid, current=cur, available=cur)
            elif acct.account_type == AccountType.CREDIT:
                cur = -round(self._rng.uniform(200, 3000), 2)
                out[aid] = Balance(account_id=aid, current=cur, available=5000 + cur, limit=5000.0)
        return out

    def _generate_transactions(
        self, account_id: str, start: datetime, end: datetime
    ) -> List[Transaction]:
        txns: List[Transaction] = []
        day = start
        while day <= end:
            count = self._rng.randint(0, 4)
            for _ in range(count):
                merchant, category, ttype = self._rng.choice(_MERCHANTS)
                if ttype == TransactionType.CREDIT:
                    amount = round(self._rng.uniform(500, 5000), 2)
                elif ttype == TransactionType.FEE:
                    amount = -round(self._rng.uniform(5, 35), 2)
                elif ttype == TransactionType.INTEREST:
                    amount = round(self._rng.uniform(0.5, 25), 2)
                else:
                    amount = -round(self._rng.uniform(3, 250), 2)
                tid = hashlib.sha256(f"{account_id}-{day.isoformat()}-{merchant}-{amount}".encode()).hexdigest()[:16]
                txns.append(Transaction(
                    transaction_id=tid,
                    account_id=account_id,
                    amount=amount,
                    date=day.replace(hour=self._rng.randint(6, 22), minute=self._rng.randint(0, 59)),
                    description=merchant,
                    transaction_type=ttype,
                    status=TransactionStatus.POSTED if self._rng.random() > 0.1 else TransactionStatus.PENDING,
                    category=category,
                    merchant_name=merchant,
                    pending=self._rng.random() < 0.1,
                ))
            day += timedelta(days=1)
        return txns
