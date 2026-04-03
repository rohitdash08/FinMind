"""
Bank Sync Connector Architecture (issue #75)

Pluggable architecture for bank integrations.
Each connector implements a standard interface for import & refresh.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional, Any
from decimal import Decimal


# -----------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------

@dataclass
class SyncTransaction:
    """Normalized transaction from any bank connector."""
    external_id: str
    date: date
    amount: Decimal
    currency: str
    description: str
    transaction_type: str = "expense"  # "expense" | "income" | "transfer"
    balance: Optional[Decimal] = None
    reference: Optional[str] = None
    category_hint: Optional[str] = None
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "external_id": self.external_id,
            "date": self.date.isoformat(),
            "amount": str(self.amount),
            "currency": self.currency,
            "description": self.description,
            "transaction_type": self.transaction_type,
            "balance": str(self.balance) if self.balance is not None else None,
            "reference": self.reference,
            "category_hint": self.category_hint,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""
    connector_name: str
    account_id: str
    synced_at: str
    transactions: list[SyncTransaction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    new_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "connector": self.connector_name,
            "account_id": self.account_id,
            "synced_at": self.synced_at,
            "transactions": [t.to_dict() for t in self.transactions],
            "new_count": self.new_count,
            "duplicate_count": self.duplicate_count,
            "error_count": self.error_count,
            "errors": self.errors,
            "success": self.success,
        }


@dataclass
class ConnectorConfig:
    """Configuration for a bank connector instance."""
    connector_name: str
    credentials: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


# -----------------------------------------------------------------------
# Base connector interface
# -----------------------------------------------------------------------

class BankConnector(ABC):
    """
    Abstract base class for bank/financial institution connectors.
    All connectors must implement this interface.
    """

    NAME: str = "abstract"
    SUPPORTS_BALANCE: bool = False
    SUPPORTS_REFRESH: bool = False

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self._validated = False

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Validate that the credentials are correct and connection works."""
        ...

    @abstractmethod
    def fetch_transactions(
        self,
        account_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> list[SyncTransaction]:
        """Fetch transactions for an account in a date range."""
        ...

    def get_balance(self, account_id: str) -> Optional[Decimal]:
        """Get current account balance. Override if SUPPORTS_BALANCE=True."""
        return None

    def refresh(self, account_id: str) -> SyncResult:
        """
        High-level sync: fetch recent transactions and return structured result.
        Default: fetches last 30 days.
        """
        until = date.today()
        since = until - timedelta(days=30)

        synced_at = datetime.utcnow().isoformat()
        errors = []
        transactions = []

        try:
            transactions = self.fetch_transactions(account_id, since=since, until=until)
        except Exception as exc:
            errors.append(str(exc))
            return SyncResult(
                connector_name=self.NAME,
                account_id=account_id,
                synced_at=synced_at,
                errors=errors,
                success=False,
            )

        return SyncResult(
            connector_name=self.NAME,
            account_id=account_id,
            synced_at=synced_at,
            transactions=transactions,
            new_count=len(transactions),
            errors=errors,
            success=True,
        )

    @classmethod
    def get_name(cls) -> str:
        return cls.NAME


# -----------------------------------------------------------------------
# Connector registry
# -----------------------------------------------------------------------

_CONNECTOR_REGISTRY: dict[str, type[BankConnector]] = {}


def register_connector(cls: type[BankConnector]) -> type[BankConnector]:
    """Decorator to register a connector class."""
    _CONNECTOR_REGISTRY[cls.NAME] = cls
    return cls


def get_connector_class(name: str) -> Optional[type[BankConnector]]:
    return _CONNECTOR_REGISTRY.get(name)


def list_connectors() -> list[dict]:
    return [
        {
            "name": cls.NAME,
            "supports_balance": cls.SUPPORTS_BALANCE,
            "supports_refresh": cls.SUPPORTS_REFRESH,
        }
        for cls in _CONNECTOR_REGISTRY.values()
    ]


def create_connector(name: str, credentials: dict, options: dict = None) -> Optional[BankConnector]:
    """Factory function to instantiate a connector by name."""
    cls = get_connector_class(name)
    if not cls:
        return None
    config = ConnectorConfig(
        connector_name=name,
        credentials=credentials,
        options=options or {},
    )
    return cls(config)


# -----------------------------------------------------------------------
# Built-in connector implementations
# -----------------------------------------------------------------------

@register_connector
class CSVFileConnector(BankConnector):
    """
    CSV file connector: import transactions from a CSV string.
    Credentials: none required. Options: csv_content (str), delimiter (str).
    """
    NAME = "csv_file"
    SUPPORTS_BALANCE = False
    SUPPORTS_REFRESH = False

    def validate_credentials(self) -> bool:
        return True  # No credentials needed for CSV

    def fetch_transactions(
        self,
        account_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> list[SyncTransaction]:
        import csv
        import io
        content = self.config.options.get("csv_content", "")
        delimiter = self.config.options.get("delimiter", ",")
        if not content:
            return []

        transactions = []
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        for i, row in enumerate(reader):
            try:
                # Try common column names
                date_val = row.get("date") or row.get("Date") or row.get("DATE", "")
                amount_val = row.get("amount") or row.get("Amount") or row.get("AMOUNT", "0")
                desc_val = row.get("description") or row.get("Description") or row.get("memo", "")

                txn_date = datetime.strptime(date_val.strip(), "%Y-%m-%d").date()

                if since and txn_date < since:
                    continue
                if until and txn_date > until:
                    continue

                amount = Decimal(str(amount_val).replace(",", "").strip())
                transactions.append(SyncTransaction(
                    external_id=f"csv_{account_id}_{i}",
                    date=txn_date,
                    amount=abs(amount),
                    currency=self.config.options.get("currency", "USD"),
                    description=desc_val.strip(),
                    transaction_type="expense" if amount < 0 else "income",
                    raw_data=dict(row),
                ))
            except Exception:
                continue

        return transactions


@register_connector
class MockBankConnector(BankConnector):
    """
    Mock/test bank connector.
    Credentials: api_key (any non-empty string = valid).
    Generates synthetic transactions for testing.
    """
    NAME = "mock_bank"
    SUPPORTS_BALANCE = True
    SUPPORTS_REFRESH = True

    def validate_credentials(self) -> bool:
        return bool(self.config.credentials.get("api_key"))

    def fetch_transactions(
        self,
        account_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> list[SyncTransaction]:
        # Generate deterministic mock transactions
        until = until or date.today()
        since = since or (until - timedelta(days=30))

        txns = []
        current = since
        idx = 0
        while current <= until:
            if idx % 3 == 0:
                txns.append(SyncTransaction(
                    external_id=f"mock_{account_id}_{idx}",
                    date=current,
                    amount=Decimal("50.00"),
                    currency="USD",
                    description="Mock Grocery Store",
                    transaction_type="expense",
                    raw_data={"source": "mock"},
                ))
            current += timedelta(days=2)
            idx += 1
        return txns

    def get_balance(self, account_id: str) -> Optional[Decimal]:
        return Decimal("1234.56")


@register_connector
class PlaidConnector(BankConnector):
    """
    Plaid API connector (skeleton with real interface).
    Credentials: client_id, secret, access_token.
    """
    NAME = "plaid"
    SUPPORTS_BALANCE = True
    SUPPORTS_REFRESH = True

    def validate_credentials(self) -> bool:
        creds = self.config.credentials
        return all(k in creds for k in ("client_id", "secret", "access_token"))

    def fetch_transactions(
        self,
        account_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> list[SyncTransaction]:
        # Real implementation would call https://sandbox.plaid.com/transactions/get
        # Returning empty list as placeholder (no real API call without credentials)
        return []

    def get_balance(self, account_id: str) -> Optional[Decimal]:
        # Real implementation: call /accounts/balance/get
        return None