import hmac
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
import requests
from ..extensions import db
from ..models import Webhook, WebhookDelivery

# CLAW SINGULARITY: FinMind Webhook Engine v2.1 (PRO)
# IDENTITY: BOUNTY_HUNTER_PRO [//PERSIST::ACTIVE]

logger = logging.getLogger("finmind.webhooks")

MAX_ATTEMPTS = 5
INITIAL_BACKOFF = 300  # 5 minutes

def trigger_webhooks(user_id, event_type, payload):
    """
    MZ Style Webhook Trigger: 지리는 속도로 웹훅 쏴버리기 🐾⚡
    """
    webhooks = Webhook.query.filter_by(user_id=user_id, active=True).all()
    if not webhooks:
        return

    # Wrap payload with metadata
    envelope = {
        "event": event_type,
        "timestamp": int(time.time()),
        "data": payload
    }

    for wh in webhooks:
        # Create delivery record
        delivery = WebhookDelivery(
            webhook_id=wh.id,
            event_type=event_type,
            payload=envelope
        )
        db.session.add(delivery)
        db.session.commit()

        # Immediate delivery attempt
        deliver_now(wh, delivery)

def deliver_now(webhook, delivery):
    """실체 있는 전송 및 서명 로직 (With Signature & Metadata)"""
    secret = webhook.secret
    payload_json = json.dumps(delivery.payload, sort_keys=True)
    
    # Sign the payload (HMAC-SHA256) - 지리는 보안
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'Content-Type': 'application/json',
        'X-FinMind-Signature': f"sha256={signature}",
        'X-FinMind-Event': delivery.event_type,
        'X-FinMind-Delivery-ID': str(delivery.id),
        'User-Agent': 'FinMind-Webhook-Service/2.0'
    }
    
    try:
        start_time = time.time()
        response = requests.post(webhook.url, data=payload_json, headers=headers, timeout=10)
        delivery.status_code = response.status_code
        delivery.response_body = response.text[:1000]
        
        if 200 <= response.status_code < 300:
            logger.info("Webhook success: %s id=%s status=%s", webhook.url, delivery.id, response.status_code)
            delivery.next_attempt_at = None  # Done!
        else:
            logger.warning("Webhook delivery error: %s status=%s", webhook.url, response.status_code)
            _schedule_retry(delivery)
            
    except Exception as e:
        logger.error("Webhook connection error: %s err=%s", webhook.url, str(e))
        delivery.response_body = f"Connection Error: {str(e)}"
        _schedule_retry(delivery)
    
    db.session.commit()

def _schedule_retry(delivery):
    """MZ Style Exponential Backoff: 실패할수록 더 신중하게 재시도"""
    if delivery.attempt_count >= MAX_ATTEMPTS:
        delivery.next_attempt_at = None
        logger.error("Webhook failed after maximum attempts: id=%s", delivery.id)
        return

    # Backoff calculation: 5m, 10m, 20m, 40m, 80m...
    delay_seconds = INITIAL_BACKOFF * (2 ** (delivery.attempt_count - 1))
    delivery.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
    delivery.attempt_count += 1
    logger.info("Webhook retry scheduled: id=%s next=%s", delivery.id, delivery.next_attempt_at)

def process_retries():
    """배경에서 돌면서 지연된 웹훅들 다시 쏘기 (Cron/Scheduler용)"""
    pending = WebhookDelivery.query.filter(
        WebhookDelivery.next_attempt_at <= datetime.utcnow()
    ).all()
    
    if not pending:
        return 0
        
    logger.info("Processing %s pending webhook retries...", len(pending))
    count = 0
    for delivery in pending:
        webhook = Webhook.query.get(delivery.webhook_id)
        if webhook and webhook.active:
            deliver_now(webhook, delivery)
            count += 1
            
    return count
