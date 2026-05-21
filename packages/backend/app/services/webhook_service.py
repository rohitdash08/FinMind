import json
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
from ..extensions import db
from ..models import WebhookEndpoint, WebhookDelivery

def generate_signature(payload: str, secret: str) -> str:
    """Generate HMAC SHA-256 signature for webhook payload."""
    return hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def emit_event(user_id: int, event_type: str, payload_data: Dict[str, Any]):
    """Queue a webhook event for all active endpoints of a user."""
    endpoints = WebhookEndpoint.query.filter_by(user_id=user_id, active=True).all()
    payload_str = json.dumps(payload_data)

    for ep in endpoints:
        if ep.event_types == "*" or event_type in [t.strip() for t in ep.event_types.split(",")]:
            delivery = WebhookDelivery(
                endpoint_id=ep.id,
                event_type=event_type,
                payload=payload_str,
                status="PENDING",
                attempts=0,
                next_retry_at=datetime.utcnow()
            )
            db.session.add(delivery)
    
    db.session.commit()

def process_pending_webhooks():
    """Process pending webhooks. Meant to be called by a scheduler or background job."""
    from flask import current_app
    
    # We need an application context to query the db
    now = datetime.utcnow()
    deliveries = WebhookDelivery.query.filter(
        WebhookDelivery.status == "PENDING",
        WebhookDelivery.next_retry_at <= now
    ).all()

    for d in deliveries:
        endpoint = WebhookEndpoint.query.get(d.endpoint_id)
        if not endpoint or not endpoint.active:
            d.status = "FAILED"
            continue

        d.attempts += 1
        d.last_attempt_at = now
        
        signature = generate_signature(d.payload, endpoint.secret)
        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Event": d.event_type,
            "X-FinMind-Signature": f"sha256={signature}"
        }

        try:
            resp = requests.post(endpoint.url, data=d.payload, headers=headers, timeout=5)
            if 200 <= resp.status_code < 300:
                d.status = "SUCCESS"
            else:
                _handle_webhook_failure(d)
        except requests.RequestException:
            _handle_webhook_failure(d)
            
    db.session.commit()

def _handle_webhook_failure(delivery: WebhookDelivery):
    """Handle retry logic using exponential backoff."""
    MAX_ATTEMPTS = 5
    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = "FAILED"
    else:
        # Exponential backoff: 1m, 5m, 25m, 125m
        delay_minutes = 5 ** (delivery.attempts - 1)
        delivery.next_retry_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
