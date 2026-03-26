"""
Service layer for managing bank connections and imports.

Coordinates between the pluggable connector architecture and the
FinMind database models.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from ...extensions import db
from ...models import (
    BankConnection,
    BankConnectionAccount,
    BankImportRun,
    BankImportRunStatus,
    Expense,
)
from .base import (
    Account,
    AccountNotFoundError,
    AuthenticationError,
    BankConnector,
    ConnectorError,
    RateLimitError,
)
from .registry import ConnectorNotFoundError, ConnectorRegistry

logger = logging.getLogger("finmind.bank_connectors")


class BankConnectionService:
    """
    High-level service for managing bank connections.

    This service wraps the ``ConnectorRegistry`` and handles:
    - Connecting / disconnecting a bank account for a user
    - Syncing accounts from the connector into local database records
    - Running import jobs (full or refresh)
    - Storing encrypted credentials per-user per-connector
    """

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry

    # -------------------------------------------------------------------------
    # Connector discovery
    # -------------------------------------------------------------------------

    def list_available_connectors(self) -> list[dict[str, Any]]:
        """Return metadata for all registered connectors."""
        return self._registry.list_connectors()

    def get_connector_instance(
        self, connection: BankConnection, config_override: dict[str, Any] | None = None
    ) -> BankConnector:
        """
        Instantiate the appropriate connector for a saved bank connection.

        Args:
            connection: A ``BankConnection`` database record.
            config_override: Optional config values that override the stored
                encrypted config (e.g., during initial OAuth flow).

        Returns:
            A ``BankConnector`` instance configured for this user/connection.
        """
        config = self._load_config(connection)
        if config_override:
            config.update(config_override)
        config["user_id"] = str(connection.user_id)
        return self._registry.create(connection.connector_name, config)

    # -------------------------------------------------------------------------
    # Connection lifecycle
    # -------------------------------------------------------------------------

    def connect(
        self,
        user_id: int,
        connector_name: str,
        config: dict[str, Any],
        display_name: str | None = None,
        institution_name: str | None = None,
    ) -> BankConnection:
        """
        Establish a new bank connection for a user.

        Args:
            user_id: FinMind user ID.
            connector_name: Name of the registered connector (e.g., 'mock').
            config: Connector-specific configuration (credentials, tokens, etc.).
            display_name: Human-readable name for this connection.
            institution_name: Name of the bank/institution.

        Returns:
            The newly created ``BankConnection`` record.
        """
        try:
            connector = self._registry.create(connector_name, {**config, "user_id": str(user_id)})
            auth_status = connector.get_auth_status()
        except ConnectorNotFoundError:
            raise
        except ConnectorError as exc:
            raise AuthenticationError(f"Connector authentication failed: {exc}") from exc

        if not auth_status.connected:
            raise AuthenticationError(
                auth_status.error_message or "Connector reported not connected."
            )

        institution = institution_name or auth_status.institution_name or connector_name.title()
        display = display_name or f"{institution} Account"

        # Persist the connection
        conn_record = BankConnection(
            user_id=user_id,
            connector_name=connector_name,
            display_name=display,
            status="active",
            config_encrypted=self._encrypt_config(config),
            institution_name=institution,
        )
        db.session.add(conn_record)
        db.session.flush()  # Get the ID

        # Sync accounts from the connector into local DB
        self._sync_accounts(conn_record, connector)

        db.session.commit()
        logger.info(
            "Bank connection created: id=%s user=%s connector=%s",
            conn_record.id,
            user_id,
            connector_name,
        )
        return conn_record

    def disconnect(self, user_id: int, connection_id: int) -> None:
        """
        Remove a bank connection and all associated local data.

        Args:
            user_id: FinMind user ID (must own the connection).
            connection_id: ID of the connection to remove.

        Raises:
            ValueError: If the connection does not exist or belongs to another user.
        """
        conn = db.session.get(BankConnection, connection_id)
        if not conn or conn.user_id != user_id:
            raise ValueError("Connection not found.")
        db.session.delete(conn)
        db.session.commit()
        logger.info("Bank connection deleted: id=%s user=%s", connection_id, user_id)

    def list_connections(self, user_id: int) -> list[BankConnection]:
        """Return all bank connections for a user."""
        return (
            db.session.query(BankConnection)
            .filter_by(user_id=user_id)
            .order_by(BankConnection.created_at.desc())
            .all()
        )

    def refresh_auth(self, user_id: int, connection_id: int) -> BankConnection:
        """
        Re-authenticate a bank connection and update its status.

        Args:
            user_id: FinMind user ID.
            connection_id: ID of the connection to refresh.

        Returns:
            The updated ``BankConnection`` record.
        """
        conn = db.session.get(BankConnection, connection_id)
        if not conn or conn.user_id != user_id:
            raise ValueError("Connection not found.")
        connector = self.get_connector_instance(conn)
        auth_status = connector.get_auth_status()
        conn.status = "active" if auth_status.connected else "error"
        conn.last_error = auth_status.error_message
        conn.updated_at = datetime.utcnow()
        db.session.commit()
        return conn

    # -------------------------------------------------------------------------
    # Import operations
    # -------------------------------------------------------------------------

    def import_transactions(
        self,
        user_id: int,
        connection_id: int,
        account_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Run a full import of transactions for one or all accounts.

        Args:
            user_id: FinMind user ID.
            connection_id: ID of the bank connection to import from.
            account_id: Specific account to import (None = all accounts).
            from_date: Start date for import (None = all available history).
            to_date: End date for import (None = today).
            dry_run: If True, preview results without committing to DB.

        Returns:
            A summary dict with ``imported_count``, ``duplicate_count``,
            ``transactions`` (when dry_run=True), and per-account details.
        """
        conn = db.session.get(BankConnection, connection_id)
        if not conn or conn.user_id != user_id:
            raise ValueError("Connection not found.")
        connector = self.get_connector_instance(conn)

        accounts = self._get_linked_accounts(conn, account_id)
        summary: dict[str, Any] = {
            "connection_id": connection_id,
            "imported_count": 0,
            "duplicate_count": 0,
            "dry_run": dry_run,
            "accounts": [],
        }

        for bca in accounts:
            run = BankImportRun(
                bank_connection_id=conn.id,
                account_id=bca.id,
                user_id=user_id,
                status=BankImportRunStatus.STARTED.value,
            )
            db.session.add(run)
            db.session.flush()

            try:
                transactions = connector.get_transactions(
                    bca.external_account_id, from_date=from_date, to_date=to_date
                )
                rows = connector.normalize_transactions(transactions)
                result = self._commit_or_preview(
                    user_id=user_id,
                    rows=rows,
                    dry_run=dry_run,
                )

                run.imported_count = result["imported_count"]
                run.duplicate_count = result["duplicate_count"]
                run.status = BankImportRunStatus.COMPLETED.value
                run.completed_at = datetime.utcnow()

                summary["imported_count"] += result["imported_count"]
                summary["duplicate_count"] += result["duplicate_count"]
                summary["accounts"].append(
                    {
                        "account_id": bca.id,
                        "account_name": bca.account_name,
                        "imported_count": result["imported_count"],
                        "duplicate_count": result["duplicate_count"],
                        "transactions": result.get("transactions", []) if dry_run else [],
                    }
                )

            except (AuthenticationError, AccountNotFoundError, RateLimitError) as exc:
                run.status = BankImportRunStatus.FAILED.value
                run.error_message = str(exc)
                run.completed_at = datetime.utcnow()
                conn.status = "error"
                conn.last_error = str(exc)
                logger.warning(
                    "Import run failed for connection=%s account=%s: %s",
                    conn.id, bca.id, exc,
                )
                summary["accounts"].append(
                    {
                        "account_id": bca.id,
                        "account_name": bca.account_name,
                        "error": str(exc),
                    }
                )
            except ConnectorError as exc:
                run.status = BankImportRunStatus.FAILED.value
                run.error_message = str(exc)
                run.completed_at = datetime.utcnow()
                logger.exception("Unexpected connector error connection=%s", conn.id)

        # Update last_refresh timestamp on the connection
        conn.last_refresh_at = datetime.utcnow()
        conn.updated_at = datetime.utcnow()
        db.session.commit()
        return summary

    def refresh_transactions(
        self, user_id: int, connection_id: int, account_id: int | None = None
    ) -> dict[str, Any]:
        """
        Incrementally refresh transactions — only fetches new transactions
        since the last import.

        Args:
            user_id: FinMind user ID.
            connection_id: ID of the bank connection to refresh.
            account_id: Specific account to refresh (None = all accounts).

        Returns:
            Same summary dict as ``import_transactions``.
        """
        conn = db.session.get(BankConnection, connection_id)
        if not conn or conn.user_id != user_id:
            raise ValueError("Connection not found.")
        connector = self.get_connector_instance(conn)

        accounts = self._get_linked_accounts(conn, account_id)
        total_imported = 0
        total_duplicate = 0
        results = []

        for bca in accounts:
            try:
                new_transactions = connector.refresh(bca.external_account_id)
                rows = connector.normalize_transactions(new_transactions)
                result = self._commit_or_preview(user_id, rows, dry_run=False)
                total_imported += result["imported_count"]
                total_duplicate += result["duplicate_count"]
                results.append(
                    {
                        "account_id": bca.id,
                        "account_name": bca.account_name,
                        "new_transactions": len(new_transactions),
                        "imported_count": result["imported_count"],
                        "duplicate_count": result["duplicate_count"],
                    }
                )
            except ConnectorError as exc:
                results.append(
                    {
                        "account_id": bca.id,
                        "account_name": bca.account_name,
                        "error": str(exc),
                    }
                )

        conn.last_refresh_at = datetime.utcnow()
        conn.updated_at = datetime.utcnow()
        db.session.commit()

        return {
            "connection_id": connection_id,
            "imported_count": total_imported,
            "duplicate_count": total_duplicate,
            "accounts": results,
        }

    # -------------------------------------------------------------------------
    # Import history
    # -------------------------------------------------------------------------

    def list_import_runs(
        self, user_id: int, connection_id: int, limit: int = 20
    ) -> list[BankImportRun]:
        """Return recent import runs for a connection."""
        return (
            db.session.query(BankImportRun)
            .filter_by(user_id=user_id, bank_connection_id=connection_id)
            .order_by(BankImportRun.started_at.desc())
            .limit(limit)
            .all()
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _sync_accounts(
        self, conn_record: BankConnection, connector: BankConnector
    ) -> None:
        """Sync accounts from the connector into the local database."""
        try:
            accounts = connector.list_accounts()
        except ConnectorError:
            return

        for acct in accounts:
            existing = (
                db.session.query(BankConnectionAccount)
                .filter_by(
                    bank_connection_id=conn_record.id,
                    external_account_id=acct.account_id,
                )
                .first()
            )
            if existing:
                # Update balance / active status
                existing.account_name = acct.account_name
                existing.account_type = acct.account_type.value
                existing.current_balance = acct.current_balance
                existing.is_active = acct.is_active
                existing.metadata_json = acct.metadata
            else:
                bca = BankConnectionAccount(
                    bank_connection_id=conn_record.id,
                    external_account_id=acct.account_id,
                    account_name=acct.account_name,
                    account_type=acct.account_type.value,
                    currency=acct.currency,
                    current_balance=acct.current_balance,
                    mask=acct.mask,
                    is_active=acct.is_active,
                    metadata_json=acct.metadata,
                )
                db.session.add(bca)

    def _get_linked_accounts(
        self, conn: BankConnection, account_id: int | None
    ) -> list[BankConnectionAccount]:
        """Return linked account records for a connection, optionally filtered."""
        q = db.session.query(BankConnectionAccount).filter_by(
            bank_connection_id=conn.id, is_active=True
        )
        if account_id is not None:
            q = q.filter_by(id=account_id)
        return q.all()

    def _commit_or_preview(
        self, user_id: int, rows: list[dict[str, Any]], dry_run: bool
    ) -> dict[str, Any]:
        """Commit rows to the expenses table or return preview data."""
        if dry_run:
            return {
                "imported_count": sum(
                    1 for r in rows if not self._is_duplicate(user_id, r)
                ),
                "duplicate_count": sum(
                    1 for r in rows if self._is_duplicate(user_id, r)
                ),
                "transactions": rows,
            }

        imported = 0
        duplicates = 0
        for row in rows:
            if self._is_duplicate(user_id, row):
                duplicates += 1
                continue
            expense = Expense(
                user_id=user_id,
                amount=row["amount"],
                currency=row.get("currency", "USD"),
                expense_type=str(row.get("expense_type", "EXPENSE")).upper(),
                category_id=row.get("category_id"),
                notes=row["description"],
                spent_at=date.fromisoformat(row["date"]),
            )
            db.session.add(expense)
            imported += 1
        db.session.commit()
        return {"imported_count": imported, "duplicate_count": duplicates}

    def _is_duplicate(self, user_id: int, row: dict) -> bool:
        """Check if a transaction row already exists in the database."""
        return (
            db.session.query(Expense)
            .filter_by(
                user_id=user_id,
                spent_at=date.fromisoformat(row["date"]),
                amount=row["amount"],
                notes=row["description"],
            )
            .first()
            is not None
        )

    def _load_config(self, conn: BankConnection) -> dict[str, Any]:
        """Load and decrypt the stored config for a connection."""
        if not conn.config_encrypted:
            return {}
        try:
            raw = self._decrypt_config(conn.config_encrypted)
            return json.loads(raw)
        except Exception:
            return {}

    def _encrypt_config(self, config: dict[str, Any]) -> str:
        """
        Encrypt config dict to a string for storage.

        NOTE: In production, replace this with your key management solution
        (e.g., AWS KMS, HashiCorp Vault, or Fernet symmetric encryption).
        For now we use a simple base64 encoding as a placeholder — the real
        implementation should use proper encryption so that raw credentials
        are never stored in plain text in the database.
        """
        import base64

        raw = json.dumps(config)
        return base64.b64encode(raw.encode()).decode()

    def _decrypt_config(self, encrypted: str) -> str:
        """Decrypt a stored config string back to JSON."""
        import base64

        return base64.b64decode(encrypted.encode()).decode()
