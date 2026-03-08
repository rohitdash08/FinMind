import hmac
import hashlib
import json
import time
from datetime import datetime, timedelta
import requests
from app.extensions import db
from app.models import WebhookTarget, WebhookDelivery, WebhookEvent


class WebhookService:
    """Service for managing webhook events and deliveries."""

    @staticmethod
    def get_event_description(event_type: WebhookEvent) -> str:
        """Get a human-readable description of the event type."""
        descriptions = {
            WebhookEvent.EXPENSE_CREATED: "Expense created",
            WebhookEvent.EXPENSE_UPDATED: "Expense updated",
            WebhookEvent.EXPENSE_DELETED: "Expense deleted",
            WebhookEvent.BILL_CREATED: "Bill created",
            WebhookEvent.BILL_UPDATED: "Bill updated",
            WebhookEvent.BILL_DELETED: "Bill deleted",
            WebhookEvent.BILL_DUE: "Bill is due",
            WebhookEvent.SUBSCRIPTION_UPDATED: "Subscription updated",
            WebhookEvent.PROFILE_UPDATED: "Profile updated",
        }
        return descriptions.get(event_type, "Unknown event")

    @staticmethod
    def get_event_payload_example(event_type: WebhookEvent) -> dict:
        """Get an example payload for the event type."""
        examples = {
            WebhookEvent.EXPENSE_CREATED: {
                "id": 123,
                "amount": 42.50,
                "currency": "INR",
                "category_id": 45,
                "expense_type": "EXPENSE",
                "description": "Lunch with friends",
                "date": "2024-03-04",
            },
            WebhookEvent.EXPENSE_UPDATED: {
                "id": 123,
                "amount": 45.00,
                "currency": "INR",
                "category_id": 45,
                "expense_type": "EXPENSE",
                "description": "Lunch with colleagues",
                "date": "2024-03-04",
            },
            WebhookEvent.EXPENSE_DELETED: {
                "id": 123,
                "amount": 42.50,
                "currency": "INR",
                "category_id": 45,
                "expense_type": "EXPENSE",
                "description": "Lunch with friends",
                "date": "2024-03-04",
            },
            WebhookEvent.BILL_CREATED: {
                "id": 101,
                "name": "Electricity Bill",
                "amount": 1250.00,
                "currency": "INR",
                "next_due_date": "2024-03-15",
                "cadence": "MONTHLY",
                "autopay_enabled": False,
                "channel_whatsapp": False,
                "channel_email": True,
            },
            WebhookEvent.BILL_UPDATED: {
                "id": 101,
                "name": "Electricity Bill",
                "amount": 1300.00,
                "currency": "INR",
                "next_due_date": "2024-03-15",
                "cadence": "MONTHLY",
                "autopay_enabled": True,
                "channel_whatsapp": False,
                "channel_email": True,
                "active": True,
            },
            WebhookEvent.BILL_DELETED: {
                "id": 101,
            },
            WebhookEvent.BILL_DUE: {
                "id": 101,
                "name": "Electricity Bill",
                "amount": 1250.00,
                "currency": "INR",
                "due_date": "2024-03-15",
            },
            WebhookEvent.SUBSCRIPTION_UPDATED: {
                "id": 5,
                "plan_id": 2,
                "active": True,
                "started_at": "2024-01-01T00:00:00Z",
            },
            WebhookEvent.PROFILE_UPDATED: {
                "id": 42,
                "email": "user@example.com",
                "preferred_currency": "INR",
                "updated_at": "2024-03-04T10:30:00Z",
            },
        }
        return examples.get(event_type, {})

    @staticmethod
    def generate_signature(secret: str, payload: str, timestamp: str) -> str:
        """Generate HMAC SHA-256 signature for webhook payload."""
        message = f"{timestamp}.{payload}"
        return hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def validate_signature(secret: str, payload: str, timestamp: str, signature: str) -> bool:
        """Validate incoming webhook signature."""
        expected = WebhookService.generate_signature(secret, payload, timestamp)
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def trigger_event(event_type: WebhookEvent, payload: dict, user_id: int = None):
        """Trigger a webhook event to all applicable targets."""
        targets = WebhookTarget.query.filter(WebhookTarget.enabled == True)
        
        if user_id:
            targets = targets.filter(WebhookTarget.user_id == user_id)
        
        targets = targets.filter(WebhookTarget.events.contains([event_type]))
        
        for target in targets:
            delivery = WebhookDelivery(
                target_id=target.id,
                event_type=event_type,
                payload=payload,
                status="pending",
                attempt_count=0,
                next_attempt_at=datetime.utcnow()
            )
            db.session.add(delivery)
        
        db.session.commit()
        WebhookService.process_pending_deliveries()

    @staticmethod
    def process_pending_deliveries():
        """Process pending webhook deliveries with retry logic."""
        pending = WebhookDelivery.query.filter(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= datetime.utcnow()
        ).all()

        for delivery in pending:
            WebhookService.attempt_delivery(delivery)

    @staticmethod
    def attempt_delivery(delivery: WebhookDelivery):
        """Attempt to deliver a single webhook."""
        target = WebhookTarget.query.get(delivery.target_id)
        if not target or not target.enabled:
            delivery.status = "failed"
            db.session.commit()
            return

        payload = json.dumps(delivery.payload)
        timestamp = str(int(time.time()))
        signature = WebhookService.generate_signature(target.secret, payload, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Event": delivery.event_type,
            "X-FinMind-Timestamp": timestamp,
            "X-FinMind-Signature": f"sha256={signature}"
        }

        try:
            response = requests.post(
                target.url,
                data=payload,
                headers=headers,
                timeout=10
            )

            delivery.attempt_count += 1
            delivery.last_attempt_at = datetime.utcnow()
            delivery.response_status = response.status_code
            delivery.response_body = response.text

            if response.status_code in [200, 201, 202, 204]:
                delivery.status = "success"
            else:
                delivery.status = "failed"
                delivery.next_attempt_at = WebhookService.calculate_next_attempt(delivery.attempt_count)

        except Exception as e:
            delivery.attempt_count += 1
            delivery.last_attempt_at = datetime.utcnow()
            delivery.status = "failed"
            delivery.response_body = str(e)
            delivery.next_attempt_at = WebhookService.calculate_next_attempt(delivery.attempt_count)

        db.session.commit()

    @staticmethod
    def calculate_next_attempt(attempt_count: int) -> datetime:
        """Calculate exponential backoff for retries."""
        delays = [1, 5, 15, 60, 300, 1800, 3600]  # 1 min, 5 min, 15 min, 1 hour, etc.
        delay_index = min(attempt_count - 1, len(delays) - 1)
        return datetime.utcnow() + timedelta(seconds=delays[delay_index])

    @staticmethod
    def create_target(user_id: int, url: str, secret: str, events: list) -> WebhookTarget:
        """Create a new webhook target."""
        target = WebhookTarget(
            user_id=user_id,
            url=url,
            secret=secret,
            events=events,
            enabled=True
        )
        db.session.add(target)
        db.session.commit()
        return target

    @staticmethod
    def get_targets(user_id: int) -> list:
        """Get all webhook targets for a user."""
        return WebhookTarget.query.filter(WebhookTarget.user_id == user_id).all()

    @staticmethod
    def update_target(target_id: int, **kwargs):
        """Update an existing webhook target."""
        target = WebhookTarget.query.get(target_id)
        if target:
            for key, value in kwargs.items():
                setattr(target, key, value)
            target.updated_at = datetime.utcnow()
            db.session.commit()
        return target

    @staticmethod
    def delete_target(target_id: int):
        """Delete a webhook target."""
        target = WebhookTarget.query.get(target_id)
        if target:
            db.session.delete(target)
            db.session.commit()

    @staticmethod
    def redeliver(delivery_id: int):
        """Redeliver a failed webhook."""
        delivery = WebhookDelivery.query.get(delivery_id)
        if delivery:
            delivery.status = "pending"
            delivery.next_attempt_at = datetime.utcnow()
            db.session.commit()
            WebhookService.process_pending_deliveries()
