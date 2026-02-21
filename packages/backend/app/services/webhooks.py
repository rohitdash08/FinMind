import hmac
import hashlib
import json
import requests
import time
import logging
from typing import Any, Dict
from ..models import WebhookSubscription, db
from ..extensions import scheduler

logger = logging.getLogger("finmind.webhooks")

class WebhookService:
    @staticmethod
    def emit(user_id: int, event_type: str, payload: Dict[str, Any]):
        """Emit a webhook event for a specific user."""
        subscriptions = WebhookSubscription.query.filter_by(
            user_id=user_id, is_active=True
        ).all()
        
        for sub in subscriptions:
            full_payload = {
                "event": event_type,
                "timestamp": int(time.time()),
                "data": payload
            }
            # Offload delivery to background scheduler
            scheduler.add_job(
                WebhookService._deliver_with_retry,
                args=[sub.url, sub.secret, full_payload],
                id=f"webhook_{sub.id}_{int(time.time())}",
                misfire_grace_time=10
            )

    @staticmethod
    def _deliver_with_retry(url: str, secret: str, payload: Dict[str, Any], retries: int = 3):
        """Deliver webhook with exponential backoff retry logic."""
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'), 
            payload_bytes, 
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Signature": signature,
            "X-FinMind-Event": payload.get("event", "unknown"),
            "User-Agent": "FinMind-Webhook-Bot/1.0"
        }
        
        for i in range(retries):
            try:
                logger.info(f"Attempting webhook delivery to {url} (Attempt {i+1})")
                response = requests.post(url, data=payload_bytes, headers=headers, timeout=5)
                if 200 <= response.status_code < 300:
                    logger.info(f"Successfully delivered webhook to {url}")
                    return True
                logger.warning(f"Webhook delivery failed with status {response.status_code}")
            except requests.RequestException as e:
                logger.error(f"Webhook delivery error to {url}: {e}")
            
            if i < retries - 1:
                wait_time = 2 ** i
                time.sleep(wait_time)
        
        logger.error(f"Failed to deliver webhook to {url} after {retries} attempts")
        return False
