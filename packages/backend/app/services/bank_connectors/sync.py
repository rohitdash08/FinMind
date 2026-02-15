from __future__ import annotations

from datetime import datetime

from ...extensions import db
from ...models import BankConnection
from .registry import registry


class BankSyncService:
    def __init__(self, connector_registry=registry):
        self._registry = connector_registry

    def import_transactions(self, connection_id: int) -> tuple[list, str | None]:
        connection = self._get_connection(connection_id)
        connector = self._get_connector(connection.provider_id)

        connector.connect(connection.config or {})
        try:
            transactions, next_cursor = connector.import_transactions(connection.cursor)
            self._update_connection_state(connection, next_cursor)
            db.session.commit()
            return self._normalize_transactions(transactions), next_cursor
        except Exception:
            db.session.rollback()
            raise
        finally:
            connector.disconnect()

    def refresh(self, connection_id: int) -> tuple[list, str | None]:
        connection = self._get_connection(connection_id)
        connector = self._get_connector(connection.provider_id)

        connector.connect(connection.config or {})
        try:
            transactions, next_cursor = connector.refresh(connection.cursor)
            self._update_connection_state(connection, next_cursor)
            db.session.commit()
            return self._normalize_transactions(transactions), next_cursor
        except Exception:
            db.session.rollback()
            raise
        finally:
            connector.disconnect()

    @staticmethod
    def _get_connection(connection_id: int) -> BankConnection:
        connection = db.session.get(BankConnection, connection_id)
        if connection is None:
            raise ValueError(f"BankConnection not found: {connection_id}")
        return connection

    def _get_connector(self, provider_id: str):
        connector = self._registry.get(provider_id)
        if connector is None:
            raise ValueError(f"Connector not registered for provider_id={provider_id}")
        return connector

    @staticmethod
    def _update_connection_state(
        connection: BankConnection, next_cursor: str | None
    ) -> None:
        connection.cursor = next_cursor
        connection.last_synced_at = datetime.utcnow()
        connection.updated_at = datetime.utcnow()

    @staticmethod
    def _normalize_transactions(transactions: list) -> list:
        normalized = []
        for tx in transactions:
            if not isinstance(tx, dict):
                raise ValueError("Transaction payload must be a dictionary")

            tx_id = str(tx.get("id", "")).strip()
            account_id = str(tx.get("account_id", tx.get("accountId", ""))).strip()
            description = str(tx.get("description", "")).strip()
            raw_date = tx.get("date")

            if not tx_id or not account_id:
                raise ValueError(f"Invalid transaction payload: {tx}")

            try:
                amount = float(tx.get("amount", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid transaction amount in payload: {tx}"
                ) from exc

            if raw_date is None:
                raise ValueError(f"Missing transaction date in payload: {tx}")

            date = str(raw_date).strip()
            normalized.append(
                {
                    "id": tx_id,
                    "account_id": account_id,
                    "amount": amount,
                    "description": description,
                    "date": date,
                }
            )

        return normalized
