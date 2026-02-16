import hmac
import hashlib
import json
import logging
from datetime import datetime, timedelta
import requests
from ..extensions import db
from ..models import Webhook, WebhookDelivery

logger = logging.getLogger("finmind.webhooks")

def trigger_webhooks(user_id, event_type, payload):
    """
    MZ Style Webhook Trigger: 지리는 속도로 웹훅 쏴버리기 🐾⚡
    """
    webhooks = Webhook.query.filter_by(user_id=user_id, active=True).all()
    if not webhooks:
        return

    for wh in webhooks:
        # Create delivery record
        delivery = WebhookDelivery(
            webhook_id=wh.id,
            event_type=event_type,
            payload=payload
        )
        db.session.add(delivery)
        db.session.commit()

        # Attempt immediate delivery (In a real MZ app, this would be a Celery task)
        _deliver(wh, delivery)

def _deliver(webhook, delivery):
    """실체 있는 전송 및 서명 로직"""
    secret = webhook.secret
    payload_json = json.dumps(delivery.payload)
    
    # Sign the payload (HMAC-SHA256)
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'Content-Type': 'application/json',
        'X-FinMind-Signature': f"sha256={signature}",
        'X-FinMind-Event': delivery.event_type,
        'User-Agent': 'FinMind-Webhook-Bot/1.0'
    }
    
    try:
        response = requests.post(webhook.url, data=payload_json, headers=headers, timeout=5)
        delivery.status_code = response.status_code
        delivery.response_body = response.text[:500]
        
        if not (200 <= response.status_code < 300):
            logger.warning("Webhook delivery failed: %s status=%s", webhook.url, response.status_code)
            # Simple retry logic setup
            delivery.next_attempt_at = datetime.utcnow() + timedelta(minutes=5)
            
    except Exception as e:
        logger.error("Webhook connection error: %s err=%s", webhook.url, str(e))
        delivery.response_body = str(e)
        delivery.next_attempt_at = datetime.utcnow() + timedelta(minutes=10)
    
    db.session.commit()
