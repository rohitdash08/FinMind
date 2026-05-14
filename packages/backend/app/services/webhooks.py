"""Webhook Event System for FinMind.

Provides a WebhookManager that allows registering webhook URLs for specific
event types and triggering those webhooks when events occur. Includes
exponential-backoff retry logic and configurable timeout handling.

Supported event types:
    - trade_signal
    - portfolio_update
    - risk_alert
    - market_anomaly
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import requests

logger = logging.getLogger("finmind.webhooks")


class WebhookEventType(str, Enum):
    """Supported webhook event types."""

    TRADE_SIGNAL = "trade_signal"
    PORTFOLIO_UPDATE = "portfolio_update"
    RISK_ALERT = "risk_alert"
    MARKET_ANOMALY = "market_anomaly"


@dataclass
class WebhookRegistration:
    """Represents a registered webhook endpoint."""

    id: str
    url: str
    events: list[str]
    secret: str
    active: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "events": self.events,
            "secret": self.secret,
            "active": self.active,
            "created_at": self.created_at,
        }


@dataclass
class WebhookDelivery:
    """Tracks a single webhook delivery attempt."""

    id: str
    webhook_id: str
    event_type: str
    payload: dict[str, Any]
    status_code: int | None = None
    success: bool = False
    attempts: int = 0
    last_attempt_at: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "webhook_id": self.webhook_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "status_code": self.status_code,
            "success": self.success,
            "attempts": self.attempts,
            "last_attempt_at": self.last_attempt_at,
            "error": self.error,
        }


class WebhookManager:
    """Manages webhook registrations and event dispatching.

    Usage::

        manager = WebhookManager()
        manager.register_webhook(
            "https://example.com/hook",
            events=["trade_signal", "risk_alert"],
        )
        manager.trigger_event("trade_signal", {"symbol": "AAPL", "action": "BUY"})

    Args:
        max_retries: Maximum number of retry attempts per delivery (default 3).
        base_delay: Base delay in seconds for exponential backoff (default 1.0).
        max_delay: Maximum delay cap in seconds (default 60.0).
        timeout: HTTP request timeout in seconds (default 10).
        secret_key: Optional global secret for signing payloads. If not provided,
                    a per-webhook secret is generated on registration.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        timeout: float = 10.0,
        secret_key: str | None = None,
    ) -> None:
        self._webhooks: dict[str, WebhookRegistration] = {}
        self._deliveries: list[WebhookDelivery] = []
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._timeout = timeout
        self._secret_key = secret_key or ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        secret: str | None = None,
    ) -> WebhookRegistration:
        """Register a new webhook endpoint.

        Args:
            url: The HTTPS (or HTTP for testing) URL to deliver events to.
            events: List of event types to subscribe to. Defaults to all events.
            secret: Optional HMAC secret. Generated automatically if omitted.

        Returns:
            The created WebhookRegistration.

        Raises:
            ValueError: If *url* is empty or *events* contains unknown types.
        """
        if not url:
            raise ValueError("Webhook URL must not be empty")

        if events is None:
            events = [e.value for e in WebhookEventType]
        else:
            valid = {e.value for e in WebhookEventType}
            unknown = set(events) - valid
            if unknown:
                raise ValueError(f"Unknown event types: {unknown}")

        registration = WebhookRegistration(
            id=str(uuid.uuid4()),
            url=url,
            events=list(events),
            secret=secret or uuid.uuid4().hex,
        )

        with self._lock:
            self._webhooks[registration.id] = registration

        logger.info(
            "Registered webhook %s -> %s (events: %s)",
            registration.id,
            url,
            ", ".join(events),
        )
        return registration

    def unregister_webhook(self, webhook_id: str) -> bool:
        """Remove a registered webhook. Returns True if found and removed."""
        with self._lock:
            removed = self._webhooks.pop(webhook_id, None)
            if removed:
                logger.info("Unregistered webhook %s", webhook_id)
                return True
            return False

    def list_webhooks(self) -> list[WebhookRegistration]:
        """Return all registered webhooks."""
        with self._lock:
            return list(self._webhooks.values())

    def get_webhook(self, webhook_id: str) -> WebhookRegistration | None:
        """Return a single webhook by ID, or None."""
        return self._webhooks.get(webhook_id)

    # ------------------------------------------------------------------
    # Event triggering
    # ------------------------------------------------------------------

    def trigger_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> list[WebhookDelivery]:
        """Trigger an event, delivering to all matching webhooks.

        Args:
            event_type: One of the supported WebhookEventType values.
            data: Arbitrary JSON-serializable payload.

        Returns:
            List of WebhookDelivery objects (one per matching webhook).

        Raises:
            ValueError: If *event_type* is not a known event type.
        """
        valid_types = {e.value for e in WebhookEventType}
        if event_type not in valid_types:
            raise ValueError(
                f"Unknown event type '{event_type}'. Valid: {sorted(valid_types)}"
            )

        payload = {
            "event_type": event_type,
            "data": data or {},
            "timestamp": time.time(),
            "delivery_id": str(uuid.uuid4()),
        }

        deliveries: list[WebhookDelivery] = []

        with self._lock:
            matching = [
                w for w in self._webhooks.values() if w.active and event_type in w.events
            ]

        for webhook in matching:
            delivery = self._deliver(webhook, payload)
            deliveries.append(delivery)

        logger.info(
            "Event '%s' triggered → %d delivery(s)", event_type, len(deliveries)
        )
        return deliveries

    # ------------------------------------------------------------------
    # Delivery internals
    # ------------------------------------------------------------------

    def _deliver(
        self,
        webhook: WebhookRegistration,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        """Deliver a payload to a webhook with exponential-backoff retry."""
        delivery = WebhookDelivery(
            id=payload.get("delivery_id", str(uuid.uuid4())),
            webhook_id=webhook.id,
            event_type=payload["event_type"],
            payload=payload,
        )

        body = json.dumps(payload, default=str)
        signature = self._sign(webhook.secret, body)

        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Signature": signature,
            "X-FinMind-Event": payload["event_type"],
            "X-FinMind-Delivery": delivery.id,
        }

        last_error: str | None = None

        for attempt in range(1, self._max_retries + 1):
            delivery.attempts = attempt
            delivery.last_attempt_at = time.time()

            try:
                resp = requests.post(
                    webhook.url,
                    data=body,
                    headers=headers,
                    timeout=self._timeout,
                )
                delivery.status_code = resp.status_code

                if 200 <= resp.status_code < 300:
                    delivery.success = True
                    logger.info(
                        "Webhook %s delivered (status=%d, attempt=%d)",
                        webhook.id,
                        resp.status_code,
                        attempt,
                    )
                    break
                else:
                    last_error = f"HTTP {resp.status_code}"
                    logger.warning(
                        "Webhook %s returned %d (attempt %d/%d)",
                        webhook.id,
                        resp.status_code,
                        attempt,
                        self._max_retries,
                    )

            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning(
                    "Webhook %s request failed: %s (attempt %d/%d)",
                    webhook.id,
                    exc,
                    attempt,
                    self._max_retries,
                )

            if attempt < self._max_retries:
                delay = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
                logger.debug("Retrying in %.1fs …", delay)
                time.sleep(delay)

        if not delivery.success:
            delivery.error = last_error
            logger.error(
                "Webhook %s failed after %d attempts: %s",
                webhook.id,
                self._max_retries,
                last_error,
            )

        with self._lock:
            self._deliveries.append(delivery)

        return delivery

    # ------------------------------------------------------------------
    # HMAC signing
    # ------------------------------------------------------------------

    @staticmethod
    def _sign(secret: str, body: str) -> str:
        """Compute an HMAC-SHA256 signature for the payload body."""
        return hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(self, secret: str, body: str, signature: str) -> bool:
        """Verify a payload signature. Returns True if valid."""
        expected = self._sign(secret, body)
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Delivery history
    # ------------------------------------------------------------------

    def get_deliveries(
        self,
        webhook_id: str | None = None,
        event_type: str | None = None,
    ) -> list[WebhookDelivery]:
        """Retrieve delivery history, optionally filtered."""
        with self._lock:
            results = list(self._deliveries)
        if webhook_id:
            results = [d for d in results if d.webhook_id == webhook_id]
        if event_type:
            results = [d for d in results if d.event_type == event_type]
        return results

    def clear_deliveries(self) -> None:
        """Clear all stored delivery records."""
        with self._lock:
            self._deliveries.clear()
