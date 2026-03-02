"""Webhook service for event delivery."""
import hmac
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any
import requests
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models_webhook import (
    WebhookSubscription,
    WebhookDelivery,
    WebhookEventType,
    WebhookDeliveryStatus,
    WebhookStatus,
)

logger = logging.getLogger("finmind.webhook")

# Retry configuration
MAX_RETRIES = 5
RETRY_DELAYS = [60, 300, 900, 3600, 7200]  # 1min, 5min, 15min, 1hr, 2hr


def generate_signature(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify webhook signature."""
    expected = generate_signature(payload, secret)
    return hmac.compare_digest(expected, signature)


def create_delivery(
    subscription_id: int,
    event_type: str,
    payload: dict,
    scheduled_at: datetime = None,
) -> WebhookDelivery:
    """Create a new webhook delivery record."""
    delivery = WebhookDelivery(
        subscription_id=subscription_id,
        event_type=event_type,
        payload=payload,
        scheduled_at=scheduled_at or datetime.utcnow(),
    )
    db.session.add(delivery)
    db.session.commit()
    return delivery


def deliver_webhook(delivery: WebhookDelivery) -> bool:
    """Attempt to deliver a webhook."""
    subscription = WebhookSubscription.query.get(delivery.subscription_id)
    if not subscription or subscription.status != WebhookStatus.ACTIVE:
        logger.warning(f"Skipping delivery {delivery.id}: subscription inactive")
        return False

    # Prepare payload
    payload_data = {
        "id": delivery.id,
        "event": delivery.event_type,
        "created_at": datetime.utcnow().isoformat(),
        "data": delivery.payload,
    }
    payload_json = json.dumps(payload_data, separators=(",", ":"))

    # Generate signature
    signature = generate_signature(payload_json, subscription.secret)

    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Signature": f"sha256={signature}",
        "X-FinMind-Event": delivery.event_type,
        "X-FinMind-Delivery": str(delivery.id),
        "User-Agent": "FinMind-Webhook/1.0",
    }

    try:
        response = requests.post(
            subscription.url,
            data=payload_json,
            headers=headers,
            timeout=30,
        )

        delivery.response_status_code = response.status_code
        delivery.response_body = response.text[:1000]  # Limit stored response

        if response.status_code >= 200 and response.status_code < 300:
            delivery.status = WebhookDeliveryStatus.SUCCESS
            delivery.delivered_at = datetime.utcnow()
            subscription.last_triggered_at = datetime.utcnow()
            subscription.failure_count = 0
            logger.info(f"Webhook {delivery.id} delivered successfully")
            success = True
        else:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
            subscription.failure_count += 1
            logger.warning(f"Webhook {delivery.id} failed: HTTP {response.status_code}")
            success = False

    except requests.exceptions.Timeout:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.error_message = "Request timeout"
        subscription.failure_count += 1
        logger.error(f"Webhook {delivery.id} timeout")
        success = False
    except requests.exceptions.RequestException as e:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.error_message = str(e)[:500]
        subscription.failure_count += 1
        logger.error(f"Webhook {delivery.id} error: {e}")
        success = False

    # Deactivate subscription after too many failures
    if subscription.failure_count >= MAX_RETRIES * 2:
        subscription.status = WebhookStatus.FAILED
        logger.error(f"Subscription {subscription.id} deactivated due to repeated failures")

    db.session.commit()
    return success


def schedule_retry(delivery: WebhookDelivery) -> bool:
    """Schedule a retry for failed delivery."""
    if delivery.retry_count >= MAX_RETRIES:
        logger.warning(f"Max retries reached for delivery {delivery.id}")
        return False

    delay = RETRY_DELAYS[min(delivery.retry_count, len(RETRY_DELAYS) - 1)]
    delivery.scheduled_at = datetime.utcnow() + timedelta(seconds=delay)
    delivery.status = WebhookDeliveryStatus.RETRYING
    delivery.retry_count += 1
    db.session.commit()

    logger.info(f"Scheduled retry {delivery.retry_count} for delivery {delivery.id} in {delay}s")
    return True


def process_pending_deliveries():
    """Process all pending webhook deliveries."""
    now = datetime.utcnow()

    pending = WebhookDelivery.query.filter(
        WebhookDelivery.status.in_([
            WebhookDeliveryStatus.PENDING,
            WebhookDeliveryStatus.RETRYING,
        ]),
        WebhookDelivery.scheduled_at <= now,
    ).all()

    for delivery in pending:
        success = deliver_webhook(delivery)
        if not success and delivery.retry_count < MAX_RETRIES:
            schedule_retry(delivery)


def trigger_event(
    user_id: int,
    event_type: WebhookEventType,
    payload: dict,
):
    """Trigger webhook event for all active subscriptions."""
    subscriptions = WebhookSubscription.query.filter_by(
        user_id=user_id,
        status=WebhookStatus.ACTIVE,
    ).filter(
        WebhookSubscription.events.contains([event_type.value])
    ).all()

    for sub in subscriptions:
        delivery = create_delivery(
            subscription_id=sub.id,
            event_type=event_type.value,
            payload=payload,
        )
        # Attempt immediate delivery
        success = deliver_webhook(delivery)
        if not success:
            schedule_retry(delivery)

    logger.info(f"Triggered {event_type.value} for user {user_id}, {len(subscriptions)} subscriptions")
