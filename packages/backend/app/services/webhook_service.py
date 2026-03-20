import hmac
import hashlib
import json
import requests
from datetime import datetime
from threading import Thread
from flask import current_app
from ..models import WebhookSubscription, WebhookDeliveryLog
from ..extensions import db

class WebhookService:
    @staticmethod
    def _generate_signature(secret: str, payload: str) -> str:
        """Generate HMAC-SHA256 signature."""
        return hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def emit_event(user_id: int, event_type: str, data: dict):
        """
        Emit a webhook event to all active subscriptions for a user.
        Runs delivery in a background thread to avoid blocking.
        """
        # We need to use app context for database operations in a thread
        app = current_app._get_current_object()
        
        subscriptions = WebhookSubscription.query.filter_by(
            user_id=user_id, 
            active=True
        ).all()

        for sub in subscriptions:
            if event_type in sub.event_types:
                Thread(target=WebhookService._deliver_webhook, args=(app, sub.id, event_type, data)).start()

    @staticmethod
    def _deliver_webhook(app, subscription_id, event_type, data):
        """Internal method to deliver the webhook and log the result."""
        with app.app_context():
            sub = WebhookSubscription.query.get(subscription_id)
            if not sub:
                return

            payload = json.dumps({
                "event": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })
            
            signature = WebhookService._generate_signature(sub.secret_key, payload)
            
            headers = {
                "Content-Type": "application/json",
                "X-FinMind-Signature": signature,
                "X-FinMind-Timestamp": str(datetime.utcnow().timestamp())
            }

            try:
                response = requests.post(
                    sub.target_url, 
                    data=payload, 
                    headers=headers, 
                    timeout=10
                )
                success = 200 <= response.status_code < 300
                status_code = response.status_code
                response_body = response.text[:1000] # Limit log size
            except Exception as e:
                success = False
                status_code = 0
                response_body = str(e)

            # Log delivery
            log = WebhookDeliveryLog(
                subscription_id=sub.id,
                event_type=event_type,
                payload=data,
                response_status=status_code,
                response_body=response_body,
                success=success
            )
            db.session.add(log)
            db.session.commit()
