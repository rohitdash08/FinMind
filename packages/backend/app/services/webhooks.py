"""
Webhook service for delivering signed webhook events to user endpoints.

Features:
- HMAC-SHA256 signed payloads
- Automatic retry with exponential backoff
- Delivery tracking and failure handling
"""

import hmac
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from flask import current_app

from ..extensions import db
from ..models import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEndpoint,
    WebhookEvent,
    WebhookEventType,
)

logger = logging.getLogger("finmind.webhooks")

MAX_RETRY_ATTEMPTS = 5
RETRY_DELAYS = [60, 300, 900, 3600, 7200]
DELIVERY_TIMEOUT = 10


def compute_signature(payload: str, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature for webhook payload.

    Args:
        payload: JSON string of the webhook payload
        secret: Secret key from webhook endpoint configuration

    Returns:
        Hex-encoded signature string
    """
    signature = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    )
    return signature.hexdigest()


def emit_webhook_event(
    user_id: int, event_type: WebhookEventType, payload: Dict[str, Any]
) -> Optional[WebhookEvent]:
    """
    Emit a webhook event and trigger delivery to all subscribed endpoints.

    Args:
        user_id: ID of the user who owns this event
        event_type: Type of event being emitted
        payload: Event data payload

    Returns:
        Created WebhookEvent instance or None if no active endpoints
    """
    endpoints = (
        db.session.query(WebhookEndpoint)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    if not endpoints:
        logger.debug(
            "No active webhook endpoints for user_id=%s event=%s", user_id, event_type
        )
        return None

    subscribed_endpoints = []
    for endpoint in endpoints:
        try:
            events = json.loads(endpoint.events)
            if event_type.value in events or "*" in events:
                subscribed_endpoints.append(endpoint)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Invalid events JSON for endpoint_id=%s", endpoint.id, exc_info=True
            )

    if not subscribed_endpoints:
        logger.debug(
            "No endpoints subscribed to event=%s for user_id=%s", event_type, user_id
        )
        return None

    event = WebhookEvent(
        user_id=user_id, event_type=event_type, payload=json.dumps(payload)
    )
    db.session.add(event)
    db.session.flush()

    for endpoint in subscribed_endpoints:
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_id=event.id,
            status=WebhookDeliveryStatus.PENDING,
            attempt_count=0,
        )
        db.session.add(delivery)

    db.session.commit()

    logger.info(
        "Webhook event created: event_id=%s user_id=%s type=%s endpoints=%s",
        event.id,
        user_id,
        event_type,
        len(subscribed_endpoints),
    )

    for endpoint in subscribed_endpoints:
        _deliver_webhook(endpoint.id, event.id)

    return event


def _deliver_webhook(endpoint_id: int, event_id: int) -> bool:
    """
    Attempt to deliver a webhook event to an endpoint.

    Args:
        endpoint_id: ID of the webhook endpoint
        event_id: ID of the webhook event

    Returns:
        True if delivery succeeded, False otherwise
    """
    endpoint = db.session.get(WebhookEndpoint, endpoint_id)
    event = db.session.get(WebhookEvent, event_id)

    if not endpoint or not event:
        logger.error("Invalid endpoint_id=%s or event_id=%s", endpoint_id, event_id)
        return False

    delivery = (
        db.session.query(WebhookDelivery)
        .filter_by(endpoint_id=endpoint_id, event_id=event_id)
        .first()
    )

    if not delivery:
        logger.error(
            "Delivery record not found: endpoint_id=%s event_id=%s",
            endpoint_id,
            event_id,
        )
        return False

    if delivery.attempt_count >= MAX_RETRY_ATTEMPTS:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.error_message = f"Max retry attempts ({MAX_RETRY_ATTEMPTS}) exceeded"
        delivery.completed_at = datetime.utcnow()
        db.session.commit()
        logger.warning(
            "Webhook delivery failed after %s attempts: delivery_id=%s",
            MAX_RETRY_ATTEMPTS,
            delivery.id,
        )
        return False

    payload_data = json.loads(event.payload)
    webhook_payload = {
        "id": event.id,
        "type": event.event_type.value,
        "created_at": event.created_at.isoformat(),
        "data": payload_data,
    }
    payload_str = json.dumps(webhook_payload)

    signature = compute_signature(payload_str, endpoint.secret)

    delivery.attempt_count += 1
    delivery.last_attempt_at = datetime.utcnow()
    delivery.status = WebhookDeliveryStatus.RETRYING

    try:
        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Signature": signature,
            "X-FinMind-Event": event.event_type.value,
            "X-FinMind-Delivery": str(delivery.id),
        }

        response = requests.post(
            endpoint.url,
            data=payload_str,
            headers=headers,
            timeout=DELIVERY_TIMEOUT,
        )

        delivery.response_status = response.status_code
        delivery.response_body = response.text[:1000]

        if 200 <= response.status_code < 300:
            delivery.status = WebhookDeliveryStatus.SUCCESS
            delivery.completed_at = datetime.utcnow()
            delivery.next_retry_at = None
            db.session.commit()
            logger.info(
                "Webhook delivered successfully: delivery_id=%s endpoint=%s status=%s",
                delivery.id,
                endpoint.url,
                response.status_code,
            )
            return True
        else:
            delivery.error_message = (
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
            _schedule_retry(delivery)
            db.session.commit()
            logger.warning(
                "Webhook delivery failed: delivery_id=%s status=%s retry_at=%s",
                delivery.id,
                response.status_code,
                delivery.next_retry_at,
            )
            return False

    except requests.exceptions.Timeout:
        delivery.error_message = "Request timeout"
        _schedule_retry(delivery)
        db.session.commit()
        logger.warning("Webhook delivery timeout: delivery_id=%s", delivery.id)
        return False

    except requests.exceptions.RequestException as e:
        delivery.error_message = f"Request error: {str(e)[:200]}"
        _schedule_retry(delivery)
        db.session.commit()
        logger.warning(
            "Webhook delivery error: delivery_id=%s error=%s", delivery.id, str(e)
        )
        return False

    except Exception as e:
        delivery.error_message = f"Unexpected error: {str(e)[:200]}"
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.completed_at = datetime.utcnow()
        db.session.commit()
        logger.error(
            "Unexpected webhook delivery error: delivery_id=%s", delivery.id, exc_info=e
        )
        return False


def _schedule_retry(delivery: WebhookDelivery) -> None:
    """
    Schedule the next retry attempt with exponential backoff.

    Args:
        delivery: WebhookDelivery instance to schedule retry for
    """
    attempt_index = delivery.attempt_count - 1
    if attempt_index < len(RETRY_DELAYS):
        delay_seconds = RETRY_DELAYS[attempt_index]
        delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        delivery.status = WebhookDeliveryStatus.PENDING
    else:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.completed_at = datetime.utcnow()


def retry_failed_webhooks() -> int:
    """
    Retry all pending webhook deliveries that are due for retry.

    Returns:
        Number of webhooks retried
    """
    now = datetime.utcnow()
    pending_deliveries = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
            WebhookDelivery.next_retry_at <= now,
            WebhookDelivery.attempt_count < MAX_RETRY_ATTEMPTS,
        )
        .all()
    )

    count = 0
    for delivery in pending_deliveries:
        _deliver_webhook(delivery.endpoint_id, delivery.event_id)
        count += 1

    if count > 0:
        logger.info("Retried %s pending webhook deliveries", count)

    return count


def get_delivery_stats(user_id: int) -> Dict[str, Any]:
    """
    Get webhook delivery statistics for a user.

    Args:
        user_id: ID of the user

    Returns:
        Dictionary with delivery statistics
    """
    total_events = (
        db.session.query(WebhookEvent).filter_by(user_id=user_id).count()
    )

    endpoints = (
        db.session.query(WebhookEndpoint).filter_by(user_id=user_id).all()
    )
    endpoint_ids = [e.id for e in endpoints]

    if not endpoint_ids:
        return {
            "total_events": total_events,
            "total_deliveries": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "pending_deliveries": 0,
        }

    total_deliveries = (
        db.session.query(WebhookDelivery)
        .filter(WebhookDelivery.endpoint_id.in_(endpoint_ids))
        .count()
    )

    successful = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.endpoint_id.in_(endpoint_ids),
            WebhookDelivery.status == WebhookDeliveryStatus.SUCCESS,
        )
        .count()
    )

    failed = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.endpoint_id.in_(endpoint_ids),
            WebhookDelivery.status == WebhookDeliveryStatus.FAILED,
        )
        .count()
    )

    pending = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.endpoint_id.in_(endpoint_ids),
            WebhookDelivery.status.in_(
                [WebhookDeliveryStatus.PENDING, WebhookDeliveryStatus.RETRYING]
            ),
        )
        .count()
    )

    return {
        "total_events": total_events,
        "total_deliveries": total_deliveries,
        "successful_deliveries": successful,
        "failed_deliveries": failed,
        "pending_deliveries": pending,
        "success_rate": (successful / total_deliveries * 100) if total_deliveries > 0 else 0,
    }
