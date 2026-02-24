"""Service layer for bank-sync operations.

Bridges the pluggable :class:`BankConnector` interface with FinMind's
SQLAlchemy models, handling deduplication, cursor tracking, and
audit logging.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from ..connectors import BankConnector, SyncResult
from ..connectors.base import SyncStatus
from ..extensions import db
from ..models import (
    BankConnection,
    ConnectionStatus,
    Expense,
    SyncLog,
    User,
)

logger = logging.getLogger("finmind.services.bank_sync")


def connect_account(
    user_id: int,
    provider: str,
    connector: BankConnector,
    credentials: dict,
) -> BankConnection | None:
    """Authenticate and persist a new bank connection.

    Returns the :class:`BankConnection` on success or ``None`` when
    authentication fails.
    """
    if not connector.authenticate(credentials):
        return None

    accounts = connector.get_accounts()
    if not accounts:
        return None

    # Use the first account returned by the connector.
    acct = accounts[0]
    connection = BankConnection(
        user_id=user_id,
        provider=provider,
        external_account_id=acct.external_id,
        account_name=acct.name,
        account_type=acct.account_type.value,
        currency=acct.currency,
        status=ConnectionStatus.ACTIVE.value,
    )
    db.session.add(connection)
    db.session.commit()
    logger.info(
        "Bank connection created id=%s user=%s provider=%s",
        connection.id,
        user_id,
        provider,
    )
    return connection


def import_transactions(
    connection: BankConnection,
    connector: BankConnector,
    start_date: date,
    end_date: date,
) -> dict:
    """Full import of transactions for *connection*.

    Returns a summary dict ``{inserted, duplicates, status, error}``.
    """
    log = SyncLog(
        connection_id=connection.id,
        sync_type="import",
        status="RUNNING",
        started_at=datetime.utcnow(),
    )
    db.session.add(log)
    db.session.flush()

    try:
        result = connector.import_transactions(
            connection.external_account_id, start_date, end_date
        )
        inserted, duplicates = _persist_transactions(connection, result)
        log.status = result.status.value
        log.records_imported = inserted
        log.duplicates_skipped = duplicates
        log.completed_at = datetime.utcnow()

        connection.last_sync_at = datetime.utcnow()
        if result.cursor:
            connection.sync_cursor = result.cursor
        db.session.commit()
        return {
            "inserted": inserted,
            "duplicates": duplicates,
            "status": result.status.value,
            "error": result.error,
        }
    except Exception as exc:
        logger.exception("Import failed connection=%s: %s", connection.id, exc)
        log.status = SyncStatus.FAILED.value
        log.error_message = str(exc)[:500]
        log.completed_at = datetime.utcnow()
        connection.status = ConnectionStatus.ERROR.value
        db.session.commit()
        return {
            "inserted": 0,
            "duplicates": 0,
            "status": SyncStatus.FAILED.value,
            "error": str(exc),
        }


def refresh_transactions(
    connection: BankConnection,
    connector: BankConnector,
) -> dict:
    """Incremental refresh using the stored cursor.

    Returns the same summary dict as :func:`import_transactions`.
    """
    log = SyncLog(
        connection_id=connection.id,
        sync_type="refresh",
        status="RUNNING",
        started_at=datetime.utcnow(),
    )
    db.session.add(log)
    db.session.flush()

    try:
        result = connector.refresh(
            connection.external_account_id,
            cursor=connection.sync_cursor,
        )
        inserted, duplicates = _persist_transactions(connection, result)
        log.status = result.status.value
        log.records_imported = inserted
        log.duplicates_skipped = duplicates
        log.completed_at = datetime.utcnow()

        connection.last_sync_at = datetime.utcnow()
        if result.cursor:
            connection.sync_cursor = result.cursor
        connection.status = ConnectionStatus.ACTIVE.value
        db.session.commit()
        return {
            "inserted": inserted,
            "duplicates": duplicates,
            "status": result.status.value,
            "error": result.error,
        }
    except Exception as exc:
        logger.exception("Refresh failed connection=%s: %s", connection.id, exc)
        log.status = SyncStatus.FAILED.value
        log.error_message = str(exc)[:500]
        log.completed_at = datetime.utcnow()
        connection.status = ConnectionStatus.ERROR.value
        db.session.commit()
        return {
            "inserted": 0,
            "duplicates": 0,
            "status": SyncStatus.FAILED.value,
            "error": str(exc),
        }


def disconnect_account(connection: BankConnection) -> None:
    """Mark a connection as disconnected."""
    connection.status = ConnectionStatus.DISCONNECTED.value
    db.session.commit()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _persist_transactions(
    connection: BankConnection,
    result: SyncResult,
) -> tuple[int, int]:
    """Write :class:`BankTransaction` items to the expenses table.

    Returns ``(inserted, duplicates_skipped)``.
    """
    user = db.session.get(User, connection.user_id)
    preferred_currency = user.preferred_currency if user else "INR"
    inserted = 0
    duplicates = 0

    for txn in result.transactions:
        amount = Decimal(str(txn.amount)).quantize(Decimal("0.01"))
        expense_type = "INCOME" if txn.category_hint == "INCOME" else "EXPENSE"

        exists = (
            db.session.query(Expense)
            .filter_by(
                user_id=connection.user_id,
                spent_at=txn.date,
                amount=amount,
                notes=txn.description,
            )
            .first()
        )
        if exists:
            duplicates += 1
            continue

        expense = Expense(
            user_id=connection.user_id,
            amount=amount,
            currency=txn.currency or preferred_currency,
            expense_type=expense_type,
            notes=txn.description,
            spent_at=txn.date,
        )
        db.session.add(expense)
        inserted += 1

    db.session.flush()
    return inserted, duplicates
