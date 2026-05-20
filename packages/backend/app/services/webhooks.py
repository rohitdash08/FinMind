from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from flask import current_app

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger("finmind.webhooks")
WEBHOOK_EVENT_TYPES = (
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "category.created",
    "category.updated",
    "category.deleted",
    "bill.created",
    "bill.paid",
)


def emit_webhook_event(user_id: int, event_type: str, data: dict[str, Any]) -> None:
    """Best-effort signed webhook delivery with retry/failure recording."""
    if event_type not in WEBHOOK_EVENT_TYPES:
        raise ValueError(f"unsupported webhook event type: {event_type}")

    endpoints = (
        db.session.query(WebhookEndpoint)
        .filter_by(user_id=user_id, active=True)
        .order_by(WebhookEndpoint.id.asc())
        .all()
    )
    if not endpoints:
        return

    for endpoint in endpoints:
        _deliver_to_endpoint(endpoint, event_type, user_id, data)


def _deliver_to_endpoint(
    endpoint: WebhookEndpoint, event_type: str, user_id: int, data: dict[str, Any]
) -> None:
    delivery_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": delivery_id,
        "event": event_type,
        "user_id": user_id,
        "data": data,
        "created_at": created_at,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = _signature(endpoint.secret, timestamp, body)
    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Event": event_type,
        "X-FinMind-Delivery": delivery_id,
        "X-FinMind-Timestamp": timestamp,
        "X-FinMind-Signature": signature,
    }

    attempts = 0
    success = False
    status_code = None
    error = None
    max_attempts = int(current_app.config.get("WEBHOOK_MAX_ATTEMPTS", 3))
    timeout = float(current_app.config.get("WEBHOOK_TIMEOUT_SECONDS", 3))

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            response = requests.post(
                endpoint.url,
                data=body,
                headers=headers,
                timeout=timeout,
            )
            status_code = response.status_code
            if 200 <= response.status_code < 300:
                success = True
                error = None
                break
            error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            error = str(exc)
        if attempt < max_attempts:
            time.sleep(0.1 * attempt)

    db.session.add(
        WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            delivery_id=delivery_id,
            attempts=attempts,
            success=success,
            status_code=status_code,
            error=error,
        )
    )
    try:
        db.session.commit()
    except Exception:
        logger.exception("Failed to persist webhook delivery result")
        db.session.rollback()


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"
