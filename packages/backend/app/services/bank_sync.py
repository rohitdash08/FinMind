"""Bank sync service — orchestrates importing and refreshing bank data."""

import json
import logging
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import BankConnection, BankTransaction, BankConnectionStatus
from .bank_connector import ConnectorRegistry, BankConnector

logger = logging.getLogger("finmind.bank_sync")

# Ensure mock connector is registered on import
from . import bank_mock  # noqa: F401


def connect_bank(user_id: int, provider: str, credentials: dict) -> BankConnection:
    """Create a new bank connection."""
    connector = ConnectorRegistry.get(provider)
    connection_data = connector.authenticate(credentials)

    conn = BankConnection(
        user_id=user_id,
        provider=provider,
        credentials=json.dumps(connection_data),
        status=BankConnectionStatus.ACTIVE.value,
    )
    db.session.add(conn)
    db.session.commit()
    return conn


def list_bank_accounts(connection_id: int, user_id: int) -> list[dict]:
    """List accounts available through a bank connection."""
    conn = BankConnection.query.filter_by(id=connection_id, user_id=user_id).first()
    if not conn:
        raise ValueError("Connection not found")

    connector = ConnectorRegistry.get(conn.provider)
    connection_data = json.loads(conn.credentials) if conn.credentials else {}
    accounts = connector.list_accounts(connection_data)

    return [
        {
            "external_id": a.external_id,
            "name": a.name,
            "account_type": a.account_type,
            "currency": a.currency,
            "balance": float(a.balance),
        }
        for a in accounts
    ]


def sync_transactions(
    connection_id: int,
    user_id: int,
    account_id: str,
    days: int = 30,
) -> dict:
    """Import transactions from a bank connection.

    Handles deduplication via external_id.

    Returns:
        Dict with imported/skipped counts.
    """
    conn = BankConnection.query.filter_by(id=connection_id, user_id=user_id).first()
    if not conn:
        raise ValueError("Connection not found")

    connector = ConnectorRegistry.get(conn.provider)
    connection_data = json.loads(conn.credentials) if conn.credentials else {}

    to_date = date.today()
    from_date = to_date - timedelta(days=days)

    try:
        transactions = connector.fetch_transactions(
            connection_data, account_id, from_date, to_date
        )
    except Exception as e:
        conn.status = BankConnectionStatus.ERROR.value
        db.session.commit()
        raise ValueError(f"Failed to fetch transactions: {e}")

    imported = 0
    skipped = 0

    for tx in transactions:
        # Dedup by external_id
        existing = BankTransaction.query.filter_by(
            connection_id=conn.id, external_id=tx.external_id
        ).first()
        if existing:
            skipped += 1
            continue

        bank_tx = BankTransaction(
            connection_id=conn.id,
            user_id=user_id,
            external_id=tx.external_id,
            amount=tx.amount,
            currency=tx.currency,
            description=tx.description,
            category=tx.category,
            transaction_date=tx.transaction_date,
        )
        db.session.add(bank_tx)
        imported += 1

    conn.last_sync_at = datetime.utcnow()
    conn.status = BankConnectionStatus.ACTIVE.value
    db.session.commit()

    logger.info(
        "Sync completed connection=%s imported=%s skipped=%s",
        conn.id, imported, skipped,
    )
    return {"imported": imported, "skipped": skipped}


def refresh_connection(connection_id: int, user_id: int) -> dict:
    """Refresh a bank connection (e.g., renew tokens)."""
    conn = BankConnection.query.filter_by(id=connection_id, user_id=user_id).first()
    if not conn:
        raise ValueError("Connection not found")

    connector = ConnectorRegistry.get(conn.provider)
    old_data = json.loads(conn.credentials) if conn.credentials else {}

    try:
        new_data = connector.refresh_connection(old_data)
        conn.credentials = json.dumps(new_data)
        conn.status = BankConnectionStatus.ACTIVE.value
        db.session.commit()
        return {"status": "refreshed"}
    except Exception as e:
        conn.status = BankConnectionStatus.ERROR.value
        db.session.commit()
        raise ValueError(f"Refresh failed: {e}")
