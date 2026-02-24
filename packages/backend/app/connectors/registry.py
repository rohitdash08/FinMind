"""Connector registry — maps provider names to connector classes.

Usage::

    from app.connectors.registry import registry

    registry.register("mock", MockBankConnector)

    cls = registry.get("mock")
    connector = cls(config)
"""

from __future__ import annotations

import logging
from typing import Type

from .base import BankConnector

logger = logging.getLogger("finmind.connectors.registry")


class ConnectorRegistry:
    """Simple dictionary-backed registry for bank connectors."""

    def __init__(self) -> None:
        self._providers: dict[str, Type[BankConnector]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, cls: Type[BankConnector]) -> None:
        """Register *cls* under *name* (case-insensitive)."""
        key = name.strip().lower()
        if key in self._providers:
            logger.warning("Overwriting connector %r", key)
        self._providers[key] = cls
        logger.info("Registered bank connector: %s", key)

    def get(self, name: str) -> Type[BankConnector]:
        """Return the connector class for *name*.

        Raises ``KeyError`` when the provider is unknown.
        """
        key = name.strip().lower()
        if key not in self._providers:
            raise KeyError(
                f"Unknown bank connector {name!r}. "
                f"Available: {', '.join(sorted(self._providers))}"
            )
        return self._providers[key]

    def available(self) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(self._providers)

    def __contains__(self, name: str) -> bool:
        return name.strip().lower() in self._providers

    def __len__(self) -> int:
        return len(self._providers)


# Module-level singleton used across the app.
registry = ConnectorRegistry()
