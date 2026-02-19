"""
Webhook service for managing webhook delivery with signed delivery and retries.
"""
import json
import hmac
import hashlib
import secrets
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from flask import jsonify
from ..models import db, Webhook, WebhookEvent, WebhookEventType
from ..extensions import redis_client

logger = logging.getLogger(__name__)

# Constants
WEBHOOK_SIGNATURE_HEADER = "X-FinMind-Signature"
WEBHOOK_TIMESTAMP_HEADER = "X-FinMind-Timestamp"
WEBHOOK_EVENT_ID_HEADER = "X-FinMind-Event-Id"
WEBHOOK_RETRY_ATTEMPTS = 5
WEBHOOK_RETRY_BACKOFF_BASE = 60  # seconds, exponential backoff


def generate_webhook_secret() -> str:
    """Generate a cryptographically secure webhook secret."""
    return secrets.token_urlsafe(32)


def sign_webhook_payload(payload: str, secret: str) -> str:
    """
    Sign a webhook payload using HMAC-SHA256.
    
    Args:
        payload: The JSON payload string
        secret: The webhook secret
        
    Returns:
        Hex-encoded HMAC-SHA256 signature
    """
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(signature: str, payload: str, secret: str) -> bool:
    """
    Verify a webhook signature using constant-time comparison.
    
    Args:
        signature: The signature to verify
        payload: The payload that was signed
        secret: The webhook secret
        
    Returns:
        True if signature is valid, False otherwise
    """
    expected_signature = sign_webhook_payload(payload, secret)
    return hmac.compare_digest(signature, expected_signature)


def create_webhook(user_id: int, url: str, events: List[str]) -> Webhook:
    """
    Create a new webhook for a user.
    
    Args:
        user_id: The user ID
        url: The webhook URL
        events: List of event types to subscribe to
        
    Returns:
        The created Webhook instance
    """
    secret = generate_webhook_secret()
    webhook = Webhook(
        user_id=user_id,
        url=url,
        secret=secret,
        events=json.dumps(events),
        active=True
    )
    db.session.add(webhook)
    db.session.commit()
    logger.info(f"Created webhook {webhook.id} for user {user_id}")
    return webhook


def get_user_webhooks(user_id: int, active_only: bool = False) -> List[Webhook]:
    """
    Get all webhooks for a user.
    
    Args:
        user_id: The user ID
        active_only: If True, only return active webhooks
        
    Returns:
        List of Webhook instances
    """
    query = Webhook.query.filter_by(user_id=user_id)
    if active_only:
        query = query.filter_by(active=True)
    return query.all()


def delete_webhook(webhook_id: int, user_id: int) -> bool:
    """
    Delete a webhook (soft delete by marking as inactive).
    
    Args:
        webhook_id: The webhook ID
        user_id: The user ID (for authorization)
        
    Returns:
        True if deleted, False if not found or unauthorized
    """
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=user_id).first()
    if not webhook:
        return False
    
    webhook.active = False
    db.session.commit()
    logger.info(f"Deleted webhook {webhook_id} for user {user_id}")
    return True


def update_webhook(webhook_id: int, user_id: int, url: Optional[str] = None, 
                   events: Optional[List[str]] = None) -> Optional[Webhook]:
    """
    Update a webhook.
    
    Args:
        webhook_id: The webhook ID
        user_id: The user ID (for authorization)
        url: New URL (optional)
        events: New list of events (optional)
        
    Returns:
        The updated Webhook, or None if not found/unauthorized
    """
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=user_id).first()
    if not webhook:
        return None
    
    if url is not None:
        webhook.url = url
    if events is not None:
        webhook.events = json.dumps(events)
    
    webhook.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info(f"Updated webhook {webhook_id} for user {user_id}")
    return webhook


def emit_event(user_id: int, event_type: str, data: Dict[str, Any]) -> None:
    """
    Emit a webhook event for a user.
    
    Args:
        user_id: The user ID
        event_type: The event type (e.g., "expense.created")
        data: Event data as a dictionary
    """
    # Get all active webhooks for this user that are subscribed to this event
    webhooks = get_user_webhooks(user_id, active_only=True)
    
    for webhook in webhooks:
        events = json.loads(webhook.events)
        if event_type not in events:
            continue
        
        # Create event record
        payload = json.dumps({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        })
        
        event = WebhookEvent(
            webhook_id=webhook.id,
            event_type=event_type,
            payload=payload,
            status="pending"
        )
        db.session.add(event)
        db.session.commit()
        
        # Queue delivery
        _queue_webhook_delivery(event.id)


def _queue_webhook_delivery(event_id: int) -> None:
    """Queue a webhook event for delivery."""
    if redis_client:
        redis_client.lpush("webhook_queue", event_id)


def deliver_webhook_events(batch_size: int = 100, delay_minutes: int = 0) -> Dict[str, Any]:
    """
    Process pending webhook events for delivery.
    
    Args:
        batch_size: Number of events to process in one batch
        delay_minutes: Minimum minutes since last attempt before retry
        
    Returns:
        Dictionary with stats about delivery
    """
    stats = {
        "processed": 0,
        "delivered": 0,
        "failed": 0,
        "errors": []
    }
    
    # Get pending events
    cutoff_time = datetime.utcnow() - timedelta(minutes=delay_minutes)
    pending_events = WebhookEvent.query.filter(
        WebhookEvent.status == "pending",
        (WebhookEvent.last_attempted_at.is_(None)) | 
        (WebhookEvent.last_attempted_at < cutoff_time),
        WebhookEvent.delivery_attempts < WEBHOOK_RETRY_ATTEMPTS
    ).order_by(WebhookEvent.created_at).limit(batch_size).all()
    
    for event in pending_events:
        stats["processed"] += 1
        try:
            _deliver_single_webhook(event)
            stats["delivered"] += 1
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append(str(e))
            logger.exception(f"Error delivering webhook event {event.id}: {e}")
    
    return stats


def _deliver_single_webhook(event: WebhookEvent) -> None:
    """
    Deliver a single webhook event.
    
    Args:
        event: The WebhookEvent to deliver
        
    Raises:
        Exception: If delivery fails
    """
    webhook = Webhook.query.get(event.webhook_id)
    if not webhook or not webhook.active:
        event.status = "failed"
        event.last_error = "Webhook not found or inactive"
        db.session.commit()
        return
    
    event.delivery_attempts += 1
    event.last_attempted_at = datetime.utcnow()
    
    # Create signature
    signature = sign_webhook_payload(event.payload, webhook.secret)
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        WEBHOOK_SIGNATURE_HEADER: signature,
        WEBHOOK_TIMESTAMP_HEADER: str(int(datetime.utcnow().timestamp())),
        WEBHOOK_EVENT_ID_HEADER: str(event.id),
        "User-Agent": "FinMind-Webhook/1.0"
    }
    
    try:
        response = requests.post(
            webhook.url,
            data=event.payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        event.status = "delivered"
        event.delivered_at = datetime.utcnow()
        event.last_error = None
        logger.info(f"Webhook event {event.id} delivered to {webhook.url}")
        
    except requests.RequestException as e:
        event.last_error = str(e)[:500]
        
        # Determine if we should retry
        if event.delivery_attempts >= WEBHOOK_RETRY_ATTEMPTS:
            event.status = "failed"
            logger.error(
                f"Webhook event {event.id} failed after {event.delivery_attempts} "
                f"attempts to {webhook.url}"
            )
        else:
            # Will be retried based on exponential backoff
            logger.warning(
                f"Webhook event {event.id} delivery attempt {event.delivery_attempts} "
                f"failed: {e}"
            )
    
    db.session.commit()


def get_webhook_event_docs() -> Dict[str, str]:
    """
    Get documentation for all supported webhook event types.
    
    Returns:
        Dictionary mapping event type to description
    """
    return {
        WebhookEventType.EXPENSE_CREATED.value: "Fired when a new expense is created",
        WebhookEventType.EXPENSE_UPDATED.value: "Fired when an expense is updated",
        WebhookEventType.EXPENSE_DELETED.value: "Fired when an expense is deleted",
        WebhookEventType.BILL_CREATED.value: "Fired when a new bill is created",
        WebhookEventType.BILL_UPDATED.value: "Fired when a bill is updated",
        WebhookEventType.BILL_DELETED.value: "Fired when a bill is deleted",
        WebhookEventType.BILL_PAID.value: "Fired when a bill is marked as paid",
        WebhookEventType.CATEGORY_CREATED.value: "Fired when a new category is created",
        WebhookEventType.CATEGORY_UPDATED.value: "Fired when a category is updated",
        WebhookEventType.CATEGORY_DELETED.value: "Fired when a category is deleted",
        WebhookEventType.REMINDER_CREATED.value: "Fired when a reminder is created",
        WebhookEventType.REMINDER_SENT.value: "Fired when a reminder is sent",
    }
