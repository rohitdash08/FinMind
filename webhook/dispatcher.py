"""Async webhook dispatcher with retry and exponential backoff."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from webhook.models import DeliveryStatus, WebhookDelivery, WebhookEndpoint, WebhookEvent
from webhook.signer import WebhookSigner

logger = logging.getLogger(__name__)

# Backoff schedule: 2^attempt seconds → 1, 2, 4, 8, 16 s
BASE_BACKOFF_SECONDS = 1
MAX_RETRIES = 5
DELIVERY_TIMEOUT = 10  # seconds per HTTP request


class WebhookDispatcher:
    """Asynchronous webhook dispatcher.

    Delivers :class:`WebhookEvent` payloads to registered
    :class:`WebhookEndpoint` targets, signing each request and retrying
    on failure with exponential backoff.

    Usage::

        dispatcher = WebhookDispatcher()
        delivery = await dispatcher.dispatch(event, endpoint)
    """

    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        base_backoff: float = BASE_BACKOFF_SECONDS,
        timeout: float = DELIVERY_TIMEOUT,
    ) -> None:
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.timeout = timeout
        self._deliveries: dict[str, WebhookDelivery] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        event: WebhookEvent,
        endpoint: WebhookEndpoint,
        session: aiohttp.ClientSession | None = None,
    ) -> WebhookDelivery:
        """Deliver *event* to *endpoint*, retrying on failure.

        Args:
            event: The event to deliver.
            endpoint: Target endpoint (must be active).
            session: Optional shared ``aiohttp`` session.

        Returns:
            A :class:`WebhookDelivery` with the final status.
        """
        delivery = WebhookDelivery(
            event_id=event.id,
            endpoint_id=endpoint.id,
            max_retries=self.max_retries,
        )
        self._deliveries[delivery.id] = delivery

        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession()

        try:
            await self._attempt_delivery(event, endpoint, delivery, session)
        finally:
            if own_session:
                await session.close()

        return delivery

    async def dispatch_to_many(
        self,
        event: WebhookEvent,
        endpoints: list[WebhookEndpoint],
    ) -> list[WebhookDelivery]:
        """Deliver *event* to multiple endpoints concurrently."""
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.dispatch(event, ep, session)
                for ep in endpoints
                if ep.is_active
            ]
            return list(await asyncio.gather(*tasks, return_exceptions=False))

    def get_delivery(self, delivery_id: str) -> WebhookDelivery | None:
        """Look up a tracked delivery by ID."""
        return self._deliveries.get(delivery_id)

    @property
    def deliveries(self) -> list[WebhookDelivery]:
        """All tracked deliveries."""
        return list(self._deliveries.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _attempt_delivery(
        self,
        event: WebhookEvent,
        endpoint: WebhookEndpoint,
        delivery: WebhookDelivery,
        session: aiohttp.ClientSession,
    ) -> None:
        signer = WebhookSigner(endpoint.secret)
        payload = self._build_payload(event)
        timestamp = event.timestamp.isoformat()
        signature = signer.sign(payload, timestamp)

        headers = {
            "Content-Type": "application/json",
            WebhookSigner.HEADER_NAME: signature,
            WebhookSigner.TIMESTAMP_HEADER: timestamp,
            "X-Webhook-Event": event.event_type,
            "X-Webhook-Event-Id": event.id,
        }

        while delivery.attempts <= self.max_retries:
            delivery.attempts += 1
            try:
                resp_code = await self._post(
                    session, str(endpoint.url), payload, headers
                )
                delivery.last_response_code = resp_code

                if 200 <= resp_code < 300:
                    delivery.status = DeliveryStatus.DELIVERED
                    delivery.delivered_at = datetime.now(timezone.utc)
                    logger.info(
                        "Delivered event %s to %s (attempt %d)",
                        event.id, endpoint.url, delivery.attempts,
                    )
                    return

                logger.warning(
                    "Non-2xx response %d from %s (attempt %d/%d)",
                    resp_code, endpoint.url, delivery.attempts,
                    self.max_retries + 1,
                )
            except Exception as exc:
                delivery.last_error = str(exc)
                logger.warning(
                    "Error delivering to %s (attempt %d/%d): %s",
                    endpoint.url, delivery.attempts,
                    self.max_retries + 1, exc,
                )

            if delivery.attempts <= self.max_retries:
                backoff = self.base_backoff * (2 ** (delivery.attempts - 1))
                delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                await asyncio.sleep(backoff)

        delivery.status = DeliveryStatus.FAILED
        logger.error(
            "Delivery %s failed after %d attempts", delivery.id, delivery.attempts
        )

    async def _post(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> int:
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
            return resp.status

    @staticmethod
    def _build_payload(event: WebhookEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "data": event.payload,
        }
