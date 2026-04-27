from __future__ import annotations

from typing import Type

from .base import BankConnector

_REGISTRY: dict[str, Type[BankConnector]] = {}


def register_connector(cls: Type[BankConnector]) -> Type[BankConnector]:
    """Class decorator that registers a connector by its ``provider_name``."""
    name = (cls.provider_name or "").strip().lower()
    if not name:
        raise ValueError(f"{cls.__name__} must define a non-empty provider_name")
    _REGISTRY[name] = cls
    return cls


def get_connector(provider_name: str) -> BankConnector:
    """Return a fresh instance of the connector for ``provider_name``."""
    key = (provider_name or "").strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise KeyError(f"Unknown bank connector: {provider_name!r}")
    return cls()


def available_connectors() -> list[Type[BankConnector]]:
    return list(_REGISTRY.values())


def list_connectors() -> list[dict]:
    """Public-facing summary of registered connectors."""
    return [
        {
            "provider": cls.provider_name,
            "display_name": cls.display_name or cls.provider_name,
            "required_credentials": list(cls.required_credentials),
        }
        for cls in _REGISTRY.values()
    ]
