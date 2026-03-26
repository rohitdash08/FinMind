"""
Connector registry — the central mechanism for the pluggable architecture.

The ``ConnectorRegistry`` singleton maintains a mapping of connector names
to their factory functions. New connectors are registered via
``connector_registry.register(name, factory)`` and instantiated via
``connector_registry.create(name, config)``.

Example::

    from app.services.bank_connectors import connector_registry

    # Register a custom connector
    def my_connector_factory(config):
        return MyBankConnector(config)

    connector_registry.register("mybank", my_connector_factory)

    # Use it
    conn = connector_registry.create("mybank", {"user_id": "123", "api_key": "..."})
"""
from __future__ import annotations

from typing import Any, Callable, Type

from .base import BankConnector, ConnectorError


class ConnectorNotFoundError(ConnectorError):
    """Raised when a requested connector name is not registered."""

    pass


class ConnectorRegistry:
    """
    Thread-safe(ish) registry for bank connectors.

    Connector factories are simply callable types or functions that accept
    a single ``config: dict[str, Any]`` argument and return a
    ``BankConnector`` instance.
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[dict[str, Any]], BankConnector]] = {}

    def register(
        self,
        name: str,
        factory: Callable[[dict[str, Any]], BankConnector] | Type[BankConnector],
    ) -> None:
        """
        Register a connector factory under ``name``.

        Args:
            name: Unique identifier for the connector (e.g., 'chase', 'mock').
            factory: A callable / class that accepts a config dict and returns
                a ``BankConnector`` instance.

        Raises:
            ValueError: If a connector with this name is already registered.
        """
        name = name.lower().strip()
        if name in self._factories:
            raise ValueError(
                f"Connector '{name}' is already registered. "
                "Use `force_register` to replace an existing factory."
            )
        self._factories[name] = factory

    def force_register(
        self,
        name: str,
        factory: Callable[[dict[str, Any]], BankConnector] | Type[BankConnector],
    ) -> None:
        """Register a connector, replacing any existing factory with the same name."""
        name = name.lower().strip()
        self._factories[name] = factory

    def create(self, name: str, config: dict[str, Any]) -> BankConnector:
        """
        Instantiate a connector by name with the given configuration.

        Args:
            name: Registered connector identifier.
            config: User-specific configuration passed to the connector's
                ``__init__``.

        Returns:
            A ``BankConnector`` instance.

        Raises:
            ConnectorNotFoundError: If no connector with this name is registered.
        """
        name = name.lower().strip()
        factory = self._factories.get(name)
        if factory is None:
            available = ", ".join(sorted(self._factories.keys())) or "(none)"
            raise ConnectorNotFoundError(
                f"No connector registered with name '{name}'. "
                f"Available connectors: {available}."
            )
        return factory(config)

    def get(self, name: str) -> Callable[[dict[str, Any]], BankConnector]:
        """
        Return the factory for a registered connector without instantiating it.

        Returns:
            The registered factory callable.

        Raises:
            ConnectorNotFoundError: If no connector with this name is registered.
        """
        name = name.lower().strip()
        factory = self._factories.get(name)
        if factory is None:
            available = ", ".join(sorted(self._factories.keys())) or "(none)"
            raise ConnectorNotFoundError(
                f"No connector registered with name '{name}'. "
                f"Available connectors: {available}."
            )
        return factory

    def list_connectors(self) -> list[dict[str, Any]]:
        """
        Return metadata for all registered connectors.

        Returns:
            List of dicts with at least ``name`` and ``display_name`` keys.
            Each dict also includes ``supports_refresh``, ``supports_oauth``,
            and other static connector metadata.
        """
        result = []
        for name, factory in self._factories.items():
            # Instantiate with empty config just to read static attributes
            try:
                # Use a sentinel config to avoid side effects during introspection
                temp_conn = factory({"_introspection": True})
                result.append(
                    {
                        "name": temp_conn.name,
                        "display_name": temp_conn.display_name,
                        "supports_refresh": temp_conn.supports_refresh,
                        "supports_oauth": temp_conn.supports_oauth,
                        "website_url": temp_conn.website_url,
                        "icon_url": temp_conn.icon_url,
                    }
                )
            except Exception:
                # Factory is not directly instantiable; use BankConnector attrs
                result.append(
                    {
                        "name": name,
                        "display_name": getattr(factory, "display_name", name.title()),
                        "supports_refresh": getattr(factory, "supports_refresh", True),
                        "supports_oauth": getattr(factory, "supports_oauth", False),
                        "website_url": getattr(factory, "website_url", None),
                        "icon_url": getattr(factory, "icon_url", None),
                    }
                )
        return result

    def is_registered(self, name: str) -> bool:
        """Return True if a connector with this name is registered."""
        return name.lower().strip() in self._factories
