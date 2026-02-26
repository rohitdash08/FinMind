"""Data models for webhook endpoints, events, and delivery tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class DeliveryStatus(str, Enum):
    """Status of a webhook delivery attempt."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookEndpoint(BaseModel):
    """A registered webhook endpoint that receives event notifications.

    Attributes:
        id: Unique endpoint identifier.
        url: HTTPS URL that will receive POST requests.
        secret: Shared secret used for HMAC-SHA256 signing.
        events: Set of event types this endpoint subscribes to.
        is_active: Whether the endpoint is currently enabled.
        created_at: Timestamp of registration.
        description: Optional human-readable label.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    url: HttpUrl
    secret: str
    events: set[str] = Field(default_factory=set)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""

    model_config = {"frozen": False}


class WebhookEvent(BaseModel):
    """An event to be dispatched to subscribed endpoints.

    Attributes:
        id: Unique event identifier.
        event_type: The event type string (e.g. ``transaction.created``).
        payload: Arbitrary JSON-serialisable event data.
        timestamp: When the event was created.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookDelivery(BaseModel):
    """Tracks a single delivery attempt of an event to an endpoint.

    Attributes:
        id: Unique delivery identifier.
        event_id: The event being delivered.
        endpoint_id: Target endpoint.
        status: Current delivery status.
        attempts: Number of delivery attempts made.
        max_retries: Maximum retry count before marking as failed.
        next_retry_at: Scheduled time for the next retry (if pending).
        last_response_code: HTTP status code from the most recent attempt.
        last_error: Error message from the most recent failed attempt.
        created_at: When the delivery record was created.
        delivered_at: When delivery succeeded (if applicable).
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_id: str
    endpoint_id: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    max_retries: int = 5
    next_retry_at: Optional[datetime] = None
    last_response_code: Optional[int] = None
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: Optional[datetime] = None

    model_config = {"frozen": False}
