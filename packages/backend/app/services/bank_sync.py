"""Bank sync orchestration service.

Coordinates between connectors, the database, and the expense
import pipeline.  Handles cursor tracking, deduplication, and
sync logging.
"""

import logging
import time
from datetime import date, datetime, timedelta

from ..connectors import (
    SyncResult,
    get_connector,
    list_providers,
)
from ..extensions import db
from ..models import BankConnection, Expense, SyncLog

logger = logging.getLogger("finmind.bank_sync")


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


def initiate_connection(
    user_id: int,
    provider: str,
    **kwargs,
) -> dict:
    """Start the consent/auth flow with a provider."""
    connector = get_connector(provider)
    consent = connector.create_consent(user_id, **kwargs)

    conn = BankConnection(
        user_id=user_id,
        provider=provider,
        status="pending",
        consent_handle=consent["consent_handle"],
        currency=kwargs.get("currency", "INR"),
    )
    db.session.add(conn)
    db.session.commit()

    logger.info(
        "Bank connection initiated id=%s provider=%s user=%s",
        conn.id,
        provider,
        user_id,
    )
    return {
        "connection_id": conn.id,
        "consent_handle": consent["consent_handle"],
        "redirect_url": consent.get("redirect_url"),
        "status": consent.get("status", "pending"),
    }


def confirm_consent(connection_id: int, user_id: int) -> dict:
    """Check consent status and discover accounts if approved."""
    conn = _get_connection(connection_id, user_id)
    connector = get_connector(conn.provider)

    status = connector.check_consent_status(conn.consent_handle)
    conn.status = status

    if status == "approved":
        accounts = connector.fetch_accounts(conn.consent_handle)
        if accounts:
            conn.account_id = accounts[0].account_id
            conn.account_label = accounts[0].label
            conn.currency = accounts[0].currency
            conn.status = "active"
        db.session.commit()

        return {
            "connection_id": conn.id,
            "status": conn.status,
            "accounts": [
                {
                    "account_id": a.account_id,
                    "label": a.label,
                    "type": a.type,
                    "currency": a.currency,
                }
                for a in accounts
            ],
        }

    db.session.commit()
    return {"connection_id": conn.id, "status": conn.status}


def select_account(connection_id: int, user_id: int, account_id: str) -> dict:
    """Select which account to sync for a connection."""
    conn = _get_connection(connection_id, user_id)
    connector = get_connector(conn.provider)
    accounts = connector.fetch_accounts(conn.consent_handle)

    matched = next((a for a in accounts if a.account_id == account_id), None)
    if not matched:
        raise ValueError(f"Account {account_id} not found")

    conn.account_id = matched.account_id
    conn.account_label = matched.label
    conn.currency = matched.currency
    conn.status = "active"
    db.session.commit()

    return {
        "connection_id": conn.id,
        "account_id": conn.account_id,
        "label": conn.account_label,
        "status": conn.status,
    }


# ---------------------------------------------------------------------------
# Sync operations
# ---------------------------------------------------------------------------


def sync_connection(
    connection_id: int,
    user_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """Full sync — fetch all transactions in a date range."""
    conn = _get_connection(connection_id, user_id)
    _require_active(conn)

    connector = get_connector(conn.provider)
    start_ms = time.monotonic()

    to_dt = to_date or date.today()
    from_dt = from_date or (to_dt - timedelta(days=180))

    log = SyncLog(
        connection_id=conn.id,
        sync_type="full",
        status="success",
    )

    try:
        result = connector.fetch_transactions(
            conn.consent_handle,
            conn.account_id,
            from_dt,
            to_dt,
        )
        imported, skipped = _import_transactions(conn.user_id, conn.currency, result)

        conn.last_sync_at = datetime.utcnow()
        if result.cursor:
            conn.sync_cursor = result.cursor

        log.records_fetched = len(result.transactions)
        log.records_imported = imported
        log.duplicates_skipped = skipped

    except Exception as exc:
        log.status = "failed"
        log.error_message = str(exc)[:2000]
        logger.exception("Sync failed connection=%s user=%s", conn.id, user_id)

    log.duration_ms = int((time.monotonic() - start_ms) * 1000)
    db.session.add(log)
    db.session.commit()

    logger.info(
        "Sync complete connection=%s type=full imported=%s skipped=%s",
        conn.id,
        log.records_imported,
        log.duplicates_skipped,
    )
    return _log_to_dict(log)


def refresh_connection(connection_id: int, user_id: int) -> dict:
    """Incremental sync using the stored cursor."""
    conn = _get_connection(connection_id, user_id)
    _require_active(conn)

    connector = get_connector(conn.provider)
    start_ms = time.monotonic()

    log = SyncLog(
        connection_id=conn.id,
        sync_type="refresh",
        status="success",
    )

    try:
        result = connector.refresh_transactions(
            conn.consent_handle,
            conn.account_id,
            conn.sync_cursor,
        )
        imported, skipped = _import_transactions(conn.user_id, conn.currency, result)

        conn.last_sync_at = datetime.utcnow()
        if result.cursor:
            conn.sync_cursor = result.cursor

        log.records_fetched = len(result.transactions)
        log.records_imported = imported
        log.duplicates_skipped = skipped

    except Exception as exc:
        log.status = "failed"
        log.error_message = str(exc)[:2000]
        logger.exception("Refresh failed connection=%s user=%s", conn.id, user_id)

    log.duration_ms = int((time.monotonic() - start_ms) * 1000)
    db.session.add(log)
    db.session.commit()

    logger.info(
        "Sync complete connection=%s type=refresh imported=%s skipped=%s",
        conn.id,
        log.records_imported,
        log.duplicates_skipped,
    )
    return _log_to_dict(log)


def disconnect(connection_id: int, user_id: int) -> None:
    """Remove a bank connection."""
    conn = _get_connection(connection_id, user_id)
    db.session.delete(conn)
    db.session.commit()
    logger.info("Disconnected bank connection=%s user=%s", connection_id, user_id)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_connections(user_id: int) -> list[dict]:
    """Return all bank connections for a user."""
    conns = (
        db.session.query(BankConnection)
        .filter_by(user_id=user_id)
        .order_by(BankConnection.created_at.desc())
        .all()
    )
    return [_conn_to_dict(c) for c in conns]


def get_sync_logs(connection_id: int, user_id: int) -> list[dict]:
    """Return sync history for a connection."""
    conn = _get_connection(connection_id, user_id)
    logs = (
        db.session.query(SyncLog)
        .filter_by(connection_id=conn.id)
        .order_by(SyncLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [_log_to_dict(entry) for entry in logs]


def get_available_providers() -> list[str]:
    """Return registered provider names."""
    return list_providers()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_connection(connection_id: int, user_id: int) -> BankConnection:
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != user_id:
        raise LookupError("Connection not found")
    return conn


def _require_active(conn: BankConnection) -> None:
    if conn.status != "active":
        raise ValueError(
            f"Connection is not active (status={conn.status}). "
            "Complete the consent flow first."
        )


def _import_transactions(
    user_id: int, currency: str, result: SyncResult
) -> tuple[int, int]:
    """Import transactions into the expenses table, skipping duplicates."""
    imported = 0
    skipped = 0

    for txn in result.transactions:
        if _is_duplicate(user_id, txn.txn_id, txn.date, txn.amount):
            skipped += 1
            continue

        expense = Expense(
            user_id=user_id,
            amount=abs(txn.amount),
            currency=txn.currency or currency,
            expense_type=txn.expense_type,
            notes=txn.description[:500],
            spent_at=date.fromisoformat(txn.date),
        )
        db.session.add(expense)
        imported += 1

    return imported, skipped


def _is_duplicate(user_id: int, txn_id: str, txn_date: str, amount: float) -> bool:
    """Check if a transaction already exists (by date + amount + notes prefix)."""
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at == date.fromisoformat(txn_date),
            Expense.amount == abs(amount),
        )
        .first()
        is not None
    )


def _conn_to_dict(conn: BankConnection) -> dict:
    return {
        "id": conn.id,
        "provider": conn.provider,
        "account_id": conn.account_id,
        "account_label": conn.account_label,
        "status": conn.status,
        "currency": conn.currency,
        "last_sync_at": (conn.last_sync_at.isoformat() if conn.last_sync_at else None),
        "created_at": conn.created_at.isoformat(),
    }


def _log_to_dict(log: SyncLog) -> dict:
    return {
        "id": log.id,
        "connection_id": log.connection_id,
        "sync_type": log.sync_type,
        "status": log.status,
        "records_fetched": log.records_fetched,
        "records_imported": log.records_imported,
        "duplicates_skipped": log.duplicates_skipped,
        "error_message": log.error_message,
        "duration_ms": log.duration_ms,
        "created_at": log.created_at.isoformat(),
    }
