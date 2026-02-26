"""Webhook endpoint registration and management (CRUD)."""

from __future__ import annotations

import logging
from typing import Sequence

from webhook.events import EventType
from webhook.models import WebhookEndpoint

logger = logging.getLogger(__name__)


class WebhookRegistry:
    """In-memory registry for webhook endpoints.

    Provides CRUD operations and subscription filtering.

    Usage::

        registry = WebhookRegistry()
        ep = registry.register(
            url="https://example.com/hook",
            secret="whsec_abc",
            events={"transaction.created"},
        )
        registry.list_for_event("transaction.created")  # [ep]
    """

    def __init__(self) -> None:
        self._endpoints: dict[str, WebhookEndpoint] = {}

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def register(
        self,
        url: str,
        secret: str,
        events: set[str] | None = None,
        description: str = "",
    ) -> WebhookEndpoint:
        """Register a new webhook endpoint.

        Args:
            url: Target URL for POST delivery.
            secret: Shared HMAC signing secret.
            events: Event types to subscribe to. ``None`` means *all*.
            description: Optional human-readable label.

        Returns:
            The newly created :class:`WebhookEndpoint`.
        """
        endpoint = WebhookEndpoint(
            url=url,
            secret=secret,
            events=events or set(),
            description=description,
        )
        self._endpoints[endpoint.id] = endpoint
        logger.info("Registered endpoint %s → %s", endpoint.id, url)
        return endpoint

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, endpoint_id: str) -> WebhookEndpoint | None:
        """Return an endpoint by ID, or ``None``."""
        return self._endpoints.get(endpoint_id)

    def list_all(self) -> list[WebhookEndpoint]:
        """Return all registered endpoints."""
        return list(self._endpoints.values())

    def list_for_event(self, event_type: str) -> list[WebhookEndpoint]:
        """Return active endpoints subscribed to *event_type*.

        An endpoint with an empty ``events`` set is treated as subscribed
        to *all* event types (wildcard).
        """
        return [
            ep
            for ep in self._endpoints.values()
            if ep.is_active
            and (not ep.events or event_type in ep.events)
        ]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        endpoint_id: str,
        *,
        url: str | None = None,
        secret: str | None = None,
        events: set[str] | None = None,
        is_active: bool | None = None,
        description: str | None = None,
    ) -> WebhookEndpoint | None:
        """Update fields on an existing endpoint.

        Only provided (non-``None``) fields are changed.

        Returns:
            The updated endpoint, or ``None`` if not found.
        """
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return None

        if url is not None:
            ep.url = url  # type: ignore[assignment]
        if secret is not None:
            ep.secret = secret
        if events is not None:
            ep.events = events
        if is_active is not None:
            ep.is_active = is_active
        if description is not None:
            ep.description = description

        logger.info("Updated endpoint %s", endpoint_id)
        return ep

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, endpoint_id: str) -> bool:
        """Remove an endpoint. Returns ``True`` if it existed."""
        removed = self._endpoints.pop(endpoint_id, None)
        if removed:
            logger.info("Deleted endpoint %s", endpoint_id)
        return removed is not None
