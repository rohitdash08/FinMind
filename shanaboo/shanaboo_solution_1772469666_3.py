import json
import time
import hmac
import hashlib
import requests
from datetime import datetime
from typing import Dict, Any, List
import config
from celery import Celery
from models import db, WebhookEndpoint, WebhookDelivery

celery = Celery('webhook_tasks', broker='redis://localhost:6379/0')

class WebhookService:
    """Service for managing webhook events and deliveries."""
    
    EVENT_TYPES = {
        'transaction.created': 'Triggered when a new transaction is created',
        'transaction.completed': 'Triggered when a transaction is marked as completed',
        'transaction.failed': 'Triggered when a transaction fails',
        'user.created': 'Triggered when a new user is created',
        'user.balance_updated': 'Triggered when user balance changes',
        'user.activated': 'Triggered when user account is activated',
        'user.deactivated': 'Triggered when user account is deactivated',
        'user.kyc_verified': 'Triggered when user KYC is verified',
        'user.kyc_rejected': 'Triggered when user KYC is rejected'
    }
    
    def __init__(self):
        self.secret = config.WEBHOOK_SECRET
    
    def emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit a webhook event to all registered endpoints."""
        if event_type not in self.EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")
        
        endpoints = WebhookEndpoint.query.filter_by(
            is_active=True,
            event_types__contains=[event_type]
        ).all()
        
        for endpoint in endpoints:
            self._queue_delivery(endpoint, event_type, payload)
    
    def _queue_delivery(self, endpoint: WebhookEndpoint, event_type: str, payload: Dict[str, Any]) -> None:
        """Queue a webhook delivery for async processing."""
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload=payload,
            status='pending'
        )
        db.session.add(delivery)
        db.session.commit()
        
        # Queue async delivery
        deliver_webhook.delay(delivery.id)
    
    def _generate_signature(self, payload: str) -> str:
        """Generate HMAC signature for webhook payload."""
        signature = hmac.new(
            self.secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

@celery.task(bind=True, max_retries=config.WEBHOOK_MAX_RETRIES)
def deliver_webhook(self, delivery_id: int) -> None:
    """Deliver webhook with retry logic."""
    delivery = WebhookDelivery.query.get(delivery_id)
    if not delivery:
        return
    
    endpoint = WebhookEndpoint.query.get(delivery.endpoint_id)
    if not endpoint or not endpoint.is_active:
        delivery.status = 'failed'
        delivery.failure_reason = 'Endpoint inactive or deleted'
        db.session.commit()
        return
    
    # Prepare webhook payload
    payload = {
        'id': delivery.id,
        'event_type': delivery.event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'data': delivery.payload
    }
    
    payload_str = json.dumps(payload, separators=(',', ':'))
    signature = WebhookService()._generate_signature(payload_str)
    
    headers = {
        'Content-Type': 'application/json',
        'X-FinMind-Signature': signature,
        'X-FinMind-Event': delivery.event_type,
        'X-FinMind-Delivery': str(delivery.id)
    }
    
    try:
        response = requests.post(
            endpoint.url,
            data=payload_str,
            headers=headers,
            timeout=config.WEBHOOK_TIMEOUT
        )
        
        delivery.status_code = response.status_code
        delivery.response_body = response.text[:1000]  # Store first 1000 chars
        
        if 200 <= response.status_code < 300:
            delivery.status = 'delivered'
            delivery.delivered_at = datetime.utcnow()
        else:
            raise requests.exceptions.RequestException(f"HTTP {response.status_code}")
            
    except Exception as e:
        delivery.status = 'retrying'
        delivery.failure_reason = str(e)
        
        # Retry with exponential backoff
        retry_count = self.request.retries
        countdown = config.WEBHOOK_RETRY_DELAY * (2 ** retry_count)
        
        raise self.retry(countdown=countdown)
    
    finally:
        db.session.commit()