"""
Webhook Event System
====================
Signed webhook delivery for key FinMind events.

Features:
  - HMAC-SHA256 signed payloads
  - Automatic retry with exponential backoff
  - Event type registration and filtering
  - Delivery logging and failure tracking

Event Types:
  - expense.created
  - expense.updated
  - expense.deleted
  - bill.due
  - bill.overdue
  - budget.exceeded
  - bank_sync.completed
  - bank_sync.failed
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Supported webhook event types."""
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_DELETED = "expense.deleted"
    BILL_DUE = "bill.due"
    BILL_OVERDUE = "bill.overdue"
    BUDGET_EXCEEDED = "budget.exceeded"
    BANK_SYNC_COMPLETED = "bank_sync.completed"
    BANK_SYNC_FAILED = "bank_sync.failed"


class DeliveryStatus(str, Enum):
    """Webhook delivery status."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookEndpoint:
    """A registered webhook endpoint."""
    id: str
    url: str
    secret: str
    events: List[str]  # Event types to subscribe to
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""
    id: str
    endpoint_id: str
    event_type: str
    payload: dict
    status: DeliveryStatus = DeliveryStatus.PENDING
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: datetime = field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None
    error: Optional[str] = None


def sign_payload(payload: str, secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for a webhook payload.

    Args:
        payload: JSON string of the webhook payload.
        secret: The shared secret for signing.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """
    Verify an HMAC-SHA256 webhook signature.

    Args:
        payload: The raw payload string.
        signature: The signature to verify.
        secret: The shared secret.

    Returns:
        True if the signature is valid.
    """
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)


class WebhookManager:
    """
    Manages webhook endpoints and event delivery.

    Usage:
        manager = WebhookManager()
        endpoint = manager.register_endpoint(
            url="https://example.com/webhook",
            secret="my-secret",
            events=["expense.created", "bill.due"],
        )
        manager.emit("expense.created", {"amount": 42.50})
    """

    def __init__(self):
        self._endpoints: Dict[str, WebhookEndpoint] = {}
        self._deliveries: List[WebhookDelivery] = []
        self._handlers: Dict[str, List[Callable]] = {}

    def register_endpoint(
        self,
        url: str,
        secret: str,
        events: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> WebhookEndpoint:
        """
        Register a new webhook endpoint.

        Args:
            url: The URL to deliver webhooks to.
            secret: Shared secret for HMAC signing.
            events: List of event types to subscribe to (None = all).
            metadata: Optional metadata.

        Returns:
            The created WebhookEndpoint.
        """
        endpoint = WebhookEndpoint(
            id=str(uuid4()),
            url=url,
            secret=secret,
            events=events or [e.value for e in EventType],
            metadata=metadata or {},
        )
        self._endpoints[endpoint.id] = endpoint
        logger.info(f"Registered webhook endpoint {endpoint.id} -> {url}")
        return endpoint

    def unregister_endpoint(self, endpoint_id: str) -> bool:
        """Remove a webhook endpoint."""
        if endpoint_id in self._endpoints:
            del self._endpoints[endpoint_id]
            return True
        return False

    def list_endpoints(self) -> List[WebhookEndpoint]:
        """List all registered endpoints."""
        return list(self._endpoints.values())

    def get_endpoint(self, endpoint_id: str) -> Optional[WebhookEndpoint]:
        """Get a specific endpoint by ID."""
        return self._endpoints.get(endpoint_id)

    def emit(self, event_type: str, data: Any) -> List[WebhookDelivery]:
        """
        Emit an event to all subscribed endpoints.

        Args:
            event_type: The event type (e.g., 'expense.created').
            data: The event data payload.

        Returns:
            List of delivery records.
        """
        deliveries = []

        for endpoint in self._endpoints.values():
            if not endpoint.active:
                continue
            if event_type not in endpoint.events:
                continue

            delivery = self._deliver(endpoint, event_type, data)
            deliveries.append(delivery)

        # Also call local handlers
        for handler in self._handlers.get(event_type, []):
            try:
                handler(event_type, data)
            except Exception as e:
                logger.error(f"Local handler error for {event_type}: {e}")

        return deliveries

    def on(self, event_type: str, handler: Callable) -> None:
        """Register a local event handler (in-process callback)."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def get_deliveries(
        self,
        endpoint_id: Optional[str] = None,
        status: Optional[DeliveryStatus] = None,
        limit: int = 50,
    ) -> List[WebhookDelivery]:
        """Get delivery history with optional filters."""
        results = self._deliveries

        if endpoint_id:
            results = [d for d in results if d.endpoint_id == endpoint_id]
        if status:
            results = [d for d in results if d.status == status]

        return results[-limit:]

    def retry_failed(self) -> List[WebhookDelivery]:
        """Retry all failed deliveries that haven't exceeded max attempts."""
        retried = []
        for delivery in self._deliveries:
            if (
                delivery.status == DeliveryStatus.FAILED
                and delivery.attempts < delivery.max_attempts
            ):
                endpoint = self._endpoints.get(delivery.endpoint_id)
                if endpoint and endpoint.active:
                    self._attempt_delivery(delivery, endpoint)
                    retried.append(delivery)
        return retried

    def _deliver(
        self, endpoint: WebhookEndpoint, event_type: str, data: Any
    ) -> WebhookDelivery:
        """Create a delivery record and attempt delivery."""
        delivery = WebhookDelivery(
            id=str(uuid4()),
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload={
                "id": str(uuid4()),
                "type": event_type,
                "created_at": datetime.utcnow().isoformat(),
                "data": data,
            },
        )
        self._deliveries.append(delivery)
        self._attempt_delivery(delivery, endpoint)
        return delivery

    def _attempt_delivery(
        self, delivery: WebhookDelivery, endpoint: WebhookEndpoint
    ) -> None:
        """
        Attempt to deliver a webhook with retry and backoff.
        """
        payload_json = json.dumps(delivery.payload, default=str)
        signature = sign_payload(payload_json, endpoint.secret)

        for attempt in range(delivery.max_attempts - delivery.attempts):
            delivery.attempts += 1
            delivery.status = DeliveryStatus.RETRYING

            try:
                req = urllib.request.Request(
                    endpoint.url,
                    data=payload_json.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": f"sha256={signature}",
                        "X-Webhook-Event": delivery.event_type,
                        "X-Webhook-Delivery-Id": delivery.id,
                        "User-Agent": "FinMind-Webhooks/1.0",
                    },
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=10) as response:
                    delivery.status_code = response.status
                    delivery.response_body = response.read().decode("utf-8")[:500]

                    if 200 <= response.status < 300:
                        delivery.status = DeliveryStatus.SUCCESS
                        delivery.delivered_at = datetime.utcnow()
                        logger.info(
                            f"Webhook delivered: {delivery.event_type} -> {endpoint.url}"
                        )
                        return

            except urllib.error.HTTPError as e:
                delivery.status_code = e.code
                delivery.error = str(e)
                logger.warning(
                    f"Webhook delivery failed ({e.code}): {endpoint.url}"
                )
            except Exception as e:
                delivery.error = str(e)
                logger.warning(f"Webhook delivery error: {e}")

            # Exponential backoff before retry
            if attempt < delivery.max_attempts - delivery.attempts - 1:
                backoff = 2 ** attempt
                time.sleep(min(backoff, 30))

        delivery.status = DeliveryStatus.FAILED
        logger.error(
            f"Webhook delivery failed after {delivery.attempts} attempts: "
            f"{delivery.event_type} -> {endpoint.url}"
        )


# Global webhook manager instance
webhook_manager = WebhookManager()


def emit_event(event_type: str, data: Any) -> List[WebhookDelivery]:
    """Convenience function to emit events via the global manager."""
    return webhook_manager.emit(event_type, data)
