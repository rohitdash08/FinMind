"""FastAPI middleware for automatic webhook dispatching."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from webhook.dispatcher import WebhookDispatcher
from webhook.events import EventType
from webhook.models import WebhookEvent
from webhook.registry import WebhookRegistry

logger = logging.getLogger(__name__)


class WebhookManager:
    """High-level façade that ties registry + dispatcher together.

    Designed for easy integration with FastAPI, Flask, or any Python app.

    Usage::

        manager = WebhookManager()
        manager.register_endpoint(
            url="https://example.com/hook",
            secret="whsec_abc",
            events={"transaction.created"},
        )
        await manager.emit("transaction.created", {"id": "txn_1", "amount": 42.0})
    """

    def __init__(
        self,
        registry: WebhookRegistry | None = None,
        dispatcher: WebhookDispatcher | None = None,
    ) -> None:
        self.registry = registry or WebhookRegistry()
        self.dispatcher = dispatcher or WebhookDispatcher()

    def register_endpoint(
        self,
        url: str,
        secret: str,
        events: set[str] | None = None,
        description: str = "",
    ) -> str:
        """Register an endpoint and return its ID."""
        ep = self.registry.register(url, secret, events, description)
        return ep.id

    async def emit(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> list[str]:
        """Emit an event to all matching endpoints.

        Args:
            event_type: Event type string (e.g. ``transaction.created``).
            data: Arbitrary event payload.

        Returns:
            List of delivery IDs.
        """
        event = WebhookEvent(event_type=event_type, payload=data or {})
        endpoints = self.registry.list_for_event(event_type)

        if not endpoints:
            logger.debug("No endpoints for event %s", event_type)
            return []

        deliveries = await self.dispatcher.dispatch_to_many(event, endpoints)
        return [d.id for d in deliveries]

    def emit_sync(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> list[str]:
        """Synchronous wrapper around :meth:`emit` for non-async contexts."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Schedule as a task; caller must await or use fire-and-forget
            future = asyncio.ensure_future(self.emit(event_type, data))
            return []  # delivery IDs not available synchronously
        else:
            return asyncio.run(self.emit(event_type, data))


# ------------------------------------------------------------------
# FastAPI integration
# ------------------------------------------------------------------

def create_fastapi_webhook_router(manager: WebhookManager):
    """Return a FastAPI ``APIRouter`` with webhook management endpoints.

    Endpoints:
        - ``POST /webhooks`` – register a new endpoint
        - ``GET  /webhooks`` – list all endpoints
        - ``DELETE /webhooks/{id}`` – remove an endpoint
    """
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    class RegisterRequest(BaseModel):
        url: str
        secret: str
        events: set[str] | None = None
        description: str = ""

    @router.post("")
    async def register(req: RegisterRequest):
        eid = manager.register_endpoint(
            url=req.url,
            secret=req.secret,
            events=req.events,
            description=req.description,
        )
        return {"id": eid, "status": "registered"}

    @router.get("")
    async def list_endpoints():
        eps = manager.registry.list_all()
        return [
            {
                "id": ep.id,
                "url": str(ep.url),
                "events": sorted(ep.events),
                "is_active": ep.is_active,
                "description": ep.description,
            }
            for ep in eps
        ]

    @router.delete("/{endpoint_id}")
    async def delete_endpoint(endpoint_id: str):
        if not manager.registry.delete(endpoint_id):
            raise HTTPException(status_code=404, detail="Endpoint not found")
        return {"status": "deleted"}

    return router
