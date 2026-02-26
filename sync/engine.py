"""Sync engine that orchestrates import/refresh across connectors."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from connectors.base import BankConnector, ConnectorError
from connectors.registry import ConnectorRegistry, get_registry
from models.sync_state import SyncState, SyncStatus
from models.transaction import Transaction

logger = logging.getLogger(__name__)

# Type alias for sync event callbacks
SyncCallback = Callable[[str, SyncState, List[Transaction]], None]


class SyncEngine:
    """Orchestrates sync operations across multiple bank connectors.

    Manages connector lifecycle, tracks sync state per connector,
    and provides unified import/refresh across all registered connectors.

    Usage:
        engine = SyncEngine()
        engine.add_connector("mock", connector_id="demo", config={})
        engine.connect_all()
        results = engine.sync_all()
        engine.disconnect_all()
    """

    def __init__(self, registry: Optional[ConnectorRegistry] = None):
        self._registry = registry or get_registry()
        self._connectors: Dict[str, BankConnector] = {}
        self._sync_states: Dict[str, SyncState] = {}
        self._callbacks: List[SyncCallback] = []

    @property
    def connector_ids(self) -> List[str]:
        return list(self._connectors.keys())

    @property
    def sync_states(self) -> Dict[str, SyncState]:
        return dict(self._sync_states)

    def add_connector(
        self,
        connector_type: str,
        connector_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> BankConnector:
        """Add a connector to the engine.

        Args:
            connector_type: Registered connector type.
            connector_id: Unique ID for this instance.
            config: Connector configuration.

        Returns:
            The created connector instance.
        """
        connector = self._registry.create(connector_type, connector_id, config)
        cid = connector.connector_id
        if cid in self._connectors:
            raise ConnectorError(f"Connector {cid!r} already exists in engine.")
        self._connectors[cid] = connector
        self._sync_states[cid] = SyncState(connector_id=cid)
        logger.info("Added connector %s to sync engine.", cid)
        return connector

    def remove_connector(self, connector_id: str) -> None:
        """Remove a connector from the engine, disconnecting if needed."""
        connector = self._get_connector(connector_id)
        if connector.is_connected:
            try:
                connector.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting %s during removal: %s", connector_id, e)
        del self._connectors[connector_id]
        del self._sync_states[connector_id]
        logger.info("Removed connector %s from sync engine.", connector_id)

    def on_sync(self, callback: SyncCallback) -> None:
        """Register a callback invoked after each connector sync.

        Callback signature: (connector_id, sync_state, transactions) -> None
        """
        self._callbacks.append(callback)

    def connect_all(self) -> Dict[str, bool]:
        """Connect all connectors. Returns dict of connector_id -> success."""
        results: Dict[str, bool] = {}
        for cid, connector in self._connectors.items():
            try:
                connector.connect()
                results[cid] = True
                logger.info("Connected: %s", cid)
            except Exception as e:
                results[cid] = False
                self._sync_states[cid].mark_failed(str(e))
                logger.error("Failed to connect %s: %s", cid, e)
        return results

    def disconnect_all(self) -> None:
        """Disconnect all connectors."""
        for cid, connector in self._connectors.items():
            try:
                if connector.is_connected:
                    connector.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting %s: %s", cid, e)

    def sync_all(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        full_import: bool = False,
    ) -> Dict[str, List[Transaction]]:
        """Sync all connectors.

        If full_import is True or connector has never synced, performs
        a full import using the date range. Otherwise does incremental refresh.

        Args:
            start_date: Start date for full imports (default: 30 days ago).
            end_date: End date for full imports (default: now).
            full_import: Force full import for all connectors.

        Returns:
            Dict of connector_id -> list of transactions.
        """
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))
        results: Dict[str, List[Transaction]] = {}

        for cid, connector in self._connectors.items():
            if not connector.is_connected:
                logger.warning("Skipping %s: not connected.", cid)
                results[cid] = []
                continue

            state = self._sync_states[cid]
            try:
                state.mark_started()
                if full_import or state.needs_sync:
                    txns = connector.import_transactions(start, end)
                    logger.info("Full import for %s: %d transactions.", cid, len(txns))
                else:
                    txns = connector.refresh()
                    logger.info("Refresh for %s: %d transactions.", cid, len(txns))

                state.mark_success(synced_count=len(txns))
                results[cid] = txns
                self._fire_callbacks(cid, state, txns)

            except Exception as e:
                state.mark_failed(str(e))
                results[cid] = []
                logger.error("Sync failed for %s: %s", cid, e)

        return results

    def sync_one(
        self,
        connector_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        full_import: bool = False,
    ) -> List[Transaction]:
        """Sync a single connector.

        Args:
            connector_id: The connector to sync.
            start_date: Start date for full import.
            end_date: End date for full import.
            full_import: Force full import.

        Returns:
            List of synced transactions.
        """
        connector = self._get_connector(connector_id)
        state = self._sync_states[connector_id]
        end = end_date or datetime.utcnow()
        start = start_date or (end - timedelta(days=30))

        state.mark_started()
        try:
            if full_import or state.needs_sync:
                txns = connector.import_transactions(start, end)
            else:
                txns = connector.refresh()
            state.mark_success(synced_count=len(txns))
            self._fire_callbacks(connector_id, state, txns)
            return txns
        except Exception as e:
            state.mark_failed(str(e))
            raise

    def get_health(self) -> Dict[str, dict]:
        """Get health status for all connectors."""
        return {
            cid: {
                "connected": self._connectors[cid].is_connected,
                "status": state.status.value,
                "healthy": state.is_healthy,
                "last_sync": state.last_sync_at.isoformat() if state.last_sync_at else None,
                "error_count": state.error_count,
                "total_synced": state.total_synced,
            }
            for cid, state in self._sync_states.items()
        }

    def _get_connector(self, connector_id: str) -> BankConnector:
        if connector_id not in self._connectors:
            raise ConnectorError(f"Connector {connector_id!r} not found in engine.")
        return self._connectors[connector_id]

    def _fire_callbacks(self, cid: str, state: SyncState, txns: List[Transaction]) -> None:
        for cb in self._callbacks:
            try:
                cb(cid, state, txns)
            except Exception as e:
                logger.warning("Sync callback error for %s: %s", cid, e)
