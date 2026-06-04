from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from ..extensions import db
from ..models import BankConnection, BankImportedTransaction, BankSyncRun, Expense, User
from .cache import cache_delete_patterns, monthly_summary_key


@dataclass(frozen=True)
class BankTransaction:
    external_id: str
    posted_at: date
    amount: Decimal
    description: str
    currency: str = "USD"
    expense_type: str = "EXPENSE"
    category_id: int | None = None


@dataclass(frozen=True)
class ConnectorDefinition:
    key: str
    name: str
    description: str
    supports_refresh: bool


class BankConnector(ABC):
    key: str
    name: str
    description: str
    supports_refresh: bool = True

    @abstractmethod
    def create_connection(
        self, *, user_id: int, config: dict[str, Any]
    ) -> BankConnection:
        """Create a sanitized connection record for this connector."""

    @abstractmethod
    def fetch_transactions(
        self, *, connection: BankConnection, since: date | None
    ) -> list[BankTransaction]:
        """Return transactions ready to import into FinMind."""

    def definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            key=self.key,
            name=self.name,
            description=self.description,
            supports_refresh=self.supports_refresh,
        )


class MockBankConnector(BankConnector):
    key = "mock"
    name = "Mock Bank"
    description = "Deterministic sample connector for development and tests."

    def create_connection(
        self, *, user_id: int, config: dict[str, Any]
    ) -> BankConnection:
        account_name = str(config.get("account_name") or "Mock Checking").strip()
        if not account_name:
            raise ValueError("account_name required")
        return BankConnection(
            user_id=user_id,
            connector_key=self.key,
            display_name=account_name[:200],
            settings_json={
                "account_name": account_name[:200],
                "currency": str(config.get("currency") or "USD")[:10],
                "transactions": config.get("transactions") or [],
            },
        )

    def fetch_transactions(
        self, *, connection: BankConnection, since: date | None
    ) -> list[BankTransaction]:
        settings = connection.settings_json or {}
        rows = settings.get("transactions") or _default_mock_transactions()
        transactions = [_transaction_from_row(row, settings) for row in rows]
        if since:
            transactions = [tx for tx in transactions if tx.posted_at >= since]
        return transactions


class AccountAggregatorConnector(BankConnector):
    key = "account_aggregator"
    name = "Account Aggregator / API Provider"
    description = (
        "Generic connector for Indian AA or bank API providers using partner "
        "portal credentials and normalized transaction payloads."
    )

    def create_connection(
        self, *, user_id: int, config: dict[str, Any]
    ) -> BankConnection:
        provider_name = _required_string(config, "provider_name")
        account_ref = _required_string(config, "account_ref")
        display_name = str(
            config.get("display_name") or f"{provider_name} {account_ref}"
        ).strip()
        return BankConnection(
            user_id=user_id,
            connector_key=self.key,
            display_name=display_name[:200],
            settings_json={
                "provider_name": provider_name[:120],
                "account_ref": account_ref[:160],
                "consent_handle": str(config.get("consent_handle") or "")[:255],
                "sync_cursor": str(config.get("sync_cursor") or "")[:255],
                "currency": str(config.get("currency") or "INR")[:10],
                # Partner credentials belong in provider portals/env-backed adapters.
                # Tests and local demos can pass normalized payloads here.
                "transactions": config.get("transactions") or [],
            },
        )

    def fetch_transactions(
        self, *, connection: BankConnection, since: date | None
    ) -> list[BankTransaction]:
        settings = connection.settings_json or {}
        rows = settings.get("transactions") or []
        transactions = [_transaction_from_row(row, settings) for row in rows]
        if since:
            transactions = [tx for tx in transactions if tx.posted_at >= since]
        return transactions


CONNECTORS: dict[str, BankConnector] = {
    AccountAggregatorConnector.key: AccountAggregatorConnector(),
    MockBankConnector.key: MockBankConnector(),
}


def list_connectors() -> list[dict[str, Any]]:
    return [
        {
            "key": definition.key,
            "name": definition.name,
            "description": definition.description,
            "supports_refresh": definition.supports_refresh,
        }
        for definition in (connector.definition() for connector in CONNECTORS.values())
    ]


def create_connection(
    *, user_id: int, connector_key: str, config: dict[str, Any]
) -> BankConnection:
    connector = _get_connector(connector_key)
    connection = connector.create_connection(user_id=user_id, config=config)
    db.session.add(connection)
    db.session.commit()
    return connection


def list_connections(*, user_id: int) -> list[BankConnection]:
    return (
        db.session.query(BankConnection)
        .filter_by(user_id=user_id)
        .order_by(BankConnection.created_at.desc())
        .all()
    )


def import_connection_transactions(
    *, user_id: int, connection_id: int, since: date | None = None
) -> dict[str, Any]:
    connection = db.session.get(BankConnection, connection_id)
    if not connection or connection.user_id != user_id:
        raise LookupError("connection not found")
    connector = _get_connector(connection.connector_key)
    run = BankSyncRun(user_id=user_id, connection_id=connection.id)
    db.session.add(run)
    db.session.flush()

    try:
        rows = connector.fetch_transactions(connection=connection, since=since)
        inserted = 0
        duplicates = 0
        touched_months: set[str] = set()
        user = db.session.get(User, user_id)
        for row in rows:
            if _is_duplicate(user_id, connection.id, row):
                duplicates += 1
                continue
            expense = Expense(
                user_id=user_id,
                category_id=row.category_id,
                amount=abs(row.amount),
                currency=row.currency or (user.preferred_currency if user else "INR"),
                expense_type=row.expense_type,
                notes=row.description[:500],
                spent_at=row.posted_at,
            )
            db.session.add(expense)
            db.session.flush()
            db.session.add(
                BankImportedTransaction(
                    user_id=user_id,
                    connection_id=connection.id,
                    expense_id=expense.id,
                    external_id=row.external_id[:255],
                )
            )
            inserted += 1
            touched_months.add(row.posted_at.strftime("%Y-%m"))

        now = datetime.utcnow()
        run.status = "completed"
        run.imported_count = inserted
        run.duplicate_count = duplicates
        run.completed_at = now
        connection.last_synced_at = now
        db.session.commit()
        for ym in touched_months:
            _invalidate_expense_cache(user_id, ym)
        return {
            "run_id": run.id,
            "connection_id": connection.id,
            "inserted": inserted,
            "duplicates": duplicates,
            "status": run.status,
        }
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:500]
        run.completed_at = datetime.utcnow()
        db.session.commit()
        raise


def refresh_connection(*, user_id: int, connection_id: int) -> dict[str, Any]:
    connection = db.session.get(BankConnection, connection_id)
    if not connection or connection.user_id != user_id:
        raise LookupError("connection not found")
    since = None
    if connection.last_synced_at:
        since = connection.last_synced_at.date() - timedelta(days=7)
    return import_connection_transactions(
        user_id=user_id,
        connection_id=connection_id,
        since=since,
    )


def connection_to_dict(connection: BankConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "connector_key": connection.connector_key,
        "display_name": connection.display_name,
        "status": connection.status,
        "last_synced_at": (
            connection.last_synced_at.isoformat() if connection.last_synced_at else None
        ),
        "created_at": connection.created_at.isoformat(),
    }


def _get_connector(connector_key: str) -> BankConnector:
    connector = CONNECTORS.get(str(connector_key or "").strip().lower())
    if connector is None:
        raise ValueError("unsupported connector")
    return connector


def _transaction_from_row(
    row: dict[str, Any], settings: dict[str, Any]
) -> BankTransaction:
    posted_at = _parse_date(row.get("date") or row.get("posted_at"))
    amount = _parse_amount(row.get("amount"))
    description = str(row.get("description") or row.get("notes") or "").strip()
    if not posted_at or amount is None or not description:
        raise ValueError("mock transactions require date, amount, and description")
    expense_type = str(row.get("expense_type") or "").upper()
    if expense_type not in {"EXPENSE", "INCOME"}:
        expense_type = (
            "INCOME" if amount > 0 and _looks_like_income(description) else "EXPENSE"
        )
    category_id = row.get("category_id")
    return BankTransaction(
        external_id=str(
            row.get("external_id") or f"{posted_at}:{amount}:{description}"
        ),
        posted_at=posted_at,
        amount=amount,
        description=description,
        currency=str(row.get("currency") or settings.get("currency") or "USD")[:10],
        expense_type=expense_type,
        category_id=int(category_id) if category_id not in (None, "", "null") else None,
    )


def _required_string(config: dict[str, Any], key: str) -> str:
    value = str(config.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} required")
    return value


def _default_mock_transactions() -> list[dict[str, Any]]:
    return [
        {
            "external_id": "mock-001",
            "date": "2026-02-10",
            "amount": "-12.50",
            "description": "Mock Coffee Shop",
            "currency": "USD",
        },
        {
            "external_id": "mock-002",
            "date": "2026-02-11",
            "amount": "-42.00",
            "description": "Mock Grocery Market",
            "currency": "USD",
        },
        {
            "external_id": "mock-003",
            "date": "2026-02-15",
            "amount": "2500.00",
            "description": "Mock Payroll",
            "currency": "USD",
            "expense_type": "INCOME",
        },
    ]


def _parse_date(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _parse_amount(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _looks_like_income(description: str) -> bool:
    upper = description.upper()
    return any(token in upper for token in ("PAYROLL", "SALARY", "REFUND", "INTEREST"))


def _is_duplicate(user_id: int, connection_id: int, row: BankTransaction) -> bool:
    imported = (
        db.session.query(BankImportedTransaction)
        .filter_by(
            user_id=user_id,
            connection_id=connection_id,
            external_id=row.external_id[:255],
        )
        .first()
    )
    if imported:
        return True
    return (
        db.session.query(Expense)
        .filter_by(
            user_id=user_id,
            spent_at=row.posted_at,
            amount=abs(row.amount),
            notes=row.description[:500],
        )
        .first()
        is not None
    )


def _invalidate_expense_cache(user_id: int, ym: str) -> None:
    cache_delete_patterns(
        [
            monthly_summary_key(user_id, ym),
            f"insights:{user_id}:*",
            f"user:{user_id}:dashboard_summary:*",
        ]
    )
