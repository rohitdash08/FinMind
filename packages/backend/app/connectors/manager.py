"""Connector Manager — registry, import, and refresh orchestration."""

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from app.connectors.base import BankConnector, BankTransaction

logger = logging.getLogger(__name__)


class ConnectorManager:
    """Registry and lifecycle manager for bank connectors.

    Usage:
        manager = ConnectorManager()
        manager.register(MockBankConnector())

        # Import transactions
        transactions = await manager.import_transactions("mock", user_id=1)

        # Refresh (re-import latest)
        await manager.refresh("mock", user_id=1)

        # List available connectors
        connectors = manager.list_connectors()
    """

    def __init__(self):
        self._connectors: dict[str, BankConnector] = {}

    # ── Registry ──────────────────────────────────────────

    def register(self, connector: BankConnector) -> None:
        """Register a bank connector instance."""
        name = connector.name
        if not name:
            raise ValueError("Connector must have a non-empty name")
        self._connectors[name] = connector
        logger.info("Registered connector: %s (%s)", name, connector.display_name)

    def unregister(self, name: str) -> None:
        """Remove a connector by name."""
        self._connectors.pop(name, None)

    def get(self, name: str) -> Optional[BankConnector]:
        """Get a connector by name."""
        return self._connectors.get(name)

    def list_connectors(self) -> list[dict]:
        """Return metadata for all registered connectors."""
        return [
            {
                "name": c.name,
                "display_name": c.display_name,
                "healthy": c.is_healthy(),
                "status": c.get_connection_status(),
            }
            for c in self._connectors.values()
        ]

    # ── Import & Refresh ──────────────────────────────────

    async def import_transactions(
        self,
        connector_name: str,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        **credentials,
    ) -> list[BankTransaction]:
        """Fetch and return normalized transactions from a connector.

        Args:
            connector_name: Registered connector name (e.g. "mock").
            user_id: The FinMind user to import for.
            from_date: Start of date range (default: 30 days ago).
            to_date: End of date range (default: today).
            **credentials: Auth credentials for the bank API.

        Returns:
            List of BankTransaction objects ready for DB insertion.

        Raises:
            ValueError: If connector not found.
        """
        connector = self._connectors.get(connector_name)
        if connector is None:
            raise ValueError(
                f"Unknown connector '{connector_name}'. "
                f"Available: {list(self._connectors.keys())}"
            )

        if from_date is None:
            from_date = date.today() - timedelta(days=30)
        if to_date is None:
            to_date = date.today()

        logger.info(
            "Importing transactions: connector=%s user=%s range=%s..%s",
            connector_name, user_id, from_date, to_date,
        )

        transactions = await connector.fetch_transactions(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            **credentials,
        )
        logger.info("Imported %d transactions", len(transactions))
        return transactions

    async def refresh(
        self,
        connector_name: str,
        user_id: int,
        **credentials,
    ) -> list[BankTransaction]:
        """Refresh: verify connection + re-import latest transactions.

        Same as import_transactions but also runs refresh_connection()
        first to validate the bank link is still alive.
        """
        connector = self._connectors.get(connector_name)
        if connector is None:
            raise ValueError(f"Unknown connector '{connector_name}'")

        healthy = await connector.refresh_connection(**credentials)
        if not healthy:
            raise ConnectionError(
                f"Connector '{connector_name}' is not healthy"
            )

        return await self.import_transactions(
            connector_name=connector_name,
            user_id=user_id,
            **credentials,
        )


# Global singleton for Flask app
_global_manager: Optional[ConnectorManager] = None


def get_connector_manager() -> ConnectorManager:
    """Get or create the global ConnectorManager singleton."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ConnectorManager()
    return _global_manager
