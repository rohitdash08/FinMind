"""
Webhook Service for FinMind

Provides signed webhook delivery with retry logic for key events:
- Expense created/updated/deleted
- Bill created/updated/paid
- Reminder triggered
- User registered
"""

import hmac
import hashlib
import time
import requests
import logging
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse
import re

from flask import current_app
from ..extensions import db
from ..models import Webhook, WebhookDelivery, WebhookDeliveryStatus, WebhookAuditLog

logger = logging.getLogger("finmind.webhooks")


class WebhookEventType(str, Enum):
    """Event types that trigger webhooks"""
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_DELETED = "expense.deleted"
    BILL_CREATED = "bill.created"
    BILL_UPDATED = "bill.updated"
    BILL_PAID = "bill.paid"
    REMINDER_TRIGGERED = "reminder.triggered"
    USER_REGISTERED = "user.registered"
    USER_DELETED = "user.deleted"


@dataclass
class WebhookPayload:
    """Webhook event payload"""
    event_type: WebhookEventType
    data: Dict[str, Any]
    timestamp: float
    user_id: Optional[int] = None
    idempotency_key: Optional[str] = None
    trace_id: Optional[str] = None


class WebhookService:
    """Service for managing webhook delivery"""

    def __init__(self) -> None:
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.max_retry_delay = 60  # seconds
        self.timeout = 10  # seconds
        self._validate_config()

    def _validate_config(self) -> bool:
        """Validate webhook service configuration"""
        errors = []
        
        try:
            # Validate timeout
            if self.timeout <= 0:
                errors.append("Timeout must be positive")
            
            # Validate retry delay
            if self.retry_delay <= 0:
                errors.append("Retry delay must be positive")
            
            if self.max_retry_delay < self.retry_delay:
                errors.append("Max retry delay must be greater than or equal to retry delay")
            
            # Validate max retries
            if self.max_retries < 0:
                errors.append("Max retries must be non-negative")
            
            if errors:
                logger.error(f"Webhook service configuration errors: {', '.join(errors)}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error validating webhook service config: {e}", exc_info=True)
            return False

    def _get_webhook_secret(self) -> str:
        """Get webhook signing secret from config"""
        secret = current_app.config.get("WEBHOOK_SECRET", "")
        if not secret:
            logger.warning("WEBHOOK_SECRET not configured, webhooks will not be signed")
        return secret

    def _generate_signature(self, payload: str) -> str:
        """Generate HMAC signature for payload"""
        secret = self._get_webhook_secret()
        if not secret:
            return ""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    def _generate_trace_id(self) -> str:
        """Generate unique trace ID for request tracking"""
        return str(uuid.uuid4())

    def _generate_idempotency_key(self, event_type: WebhookEventType, user_id: int) -> str:
        """Generate idempotency key to prevent duplicate deliveries"""
        return f"{event_type}:{user_id}:{int(time.time())}"

    def _validate_url(self, url: str) -> tuple[bool, str]:
        """Validate webhook URL"""
        if not url:
            return False, "URL is required"
        
        if len(url) > 500:
            return False, "URL exceeds maximum length of 500 characters"
        
        if not url.startswith(("http://", "https://")):
            return False, "URL must start with http:// or https://"
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False, "Invalid URL format"
            
            # Block common malicious patterns
            malicious_patterns = [
                r'javascript:',
                r'data:',
                r'file:',
                r'\.\./',
                r'\\',
            ]
            
            for pattern in malicious_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return False, f"URL contains blocked pattern: {pattern}"
            
            # Allow only common domains (optional, can be configured)
            allowed_domains = current_app.config.get('WEBHOOK_ALLOWED_DOMAINS', [])
            if allowed_domains and parsed.netloc not in allowed_domains:
                return False, f"URL domain not allowed: {parsed.netloc}"
            
            return True, "Valid"
        except Exception as e:
            return False, f"URL validation error: {str(e)}"

    def _build_payload(
        self,
        event_type: WebhookEventType,
        data: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> WebhookPayload:
        """Build webhook payload"""
        trace_id = self._generate_trace_id()
        idempotency_key = self._generate_idempotency_key(event_type, user_id or 0)
        return WebhookPayload(
            event_type=event_type,
            data=data,
            timestamp=time.time(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id
        )

    def _deliver_webhook(self, payload: WebhookPayload) -> bool:
        """Deliver webhook to registered endpoints"""
        trace_id = payload.trace_id or "unknown"
        
        logger.info(
            f"[{trace_id}] Delivering webhook event={payload.event_type.value} "
            f"user_id={payload.user_id}"
        )

        webhooks = []
        try:
            # Get all webhooks for this user
            webhooks = db.session.query(Webhook).filter_by(
                user_id=payload.user_id,
                active=True
            ).all()

            if not webhooks:
                logger.debug(f"[{trace_id}] No active webhooks for user {payload.user_id}")
                return True

            success_count = 0
            failed_count = 0

            for webhook in webhooks:
                try:
                    if not self._should_deliver_event(webhook, payload.event_type):
                        logger.debug(
                            f"[{trace_id}] Skipping webhook {webhook.id} "
                            f"(event filtered)"
                        )
                        continue

                    result = self._deliver_single_webhook(webhook, payload)
                    if result:
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"[{trace_id}] Failed to deliver webhook {webhook.id}: {e}",
                        exc_info=True
                    )

            logger.info(
                f"[{trace_id}] Webhook delivery complete: "
                f"success={success_count}, failed={failed_count}"
            )

            return success_count > 0 and failed_count == 0
        finally:
            # Clean up sessions
            try:
                db.session.close()
            except Exception as e:
                logger.error(f"Error closing session: {e}", exc_info=True)

    def _should_deliver_event(
        self,
        webhook: Webhook,
        event_type: WebhookEventType
    ) -> bool:
        """Check if webhook should receive this event based on event filters"""
        # If no events filter is set, deliver all events
        if webhook.events is None:
            return True

        # Check if this event type is in the webhook's event filter
        return event_type.value in webhook.events

    def _deliver_single_webhook(
        self,
        webhook: Webhook,
        payload: WebhookPayload
    ) -> bool:
        """Deliver webhook to a single endpoint"""
        trace_id = payload.trace_id or "unknown"
        event_value = payload.event_type.value

        logger.debug(
            f"[{trace_id}] Delivering to webhook id={webhook.id} url={webhook.url} "
            f"event={event_value}"
        )

        payload_dict = {
            "event_type": payload.event_type.value,
            "data": payload.data,
            "timestamp": payload.timestamp,
            "idempotency_key": payload.idempotency_key,
        }

        payload_json = self._serialize_payload(payload_dict)
        signature = self._generate_signature(payload_json)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event_value,
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": str(int(payload.timestamp)),
            "X-Webhook-Idempotency-Key": payload.idempotency_key or "",
            "X-Webhook-Trace-Id": trace_id,
        }

        response = None
        try:
            response = requests.post(
                webhook.url,
                json=payload_dict,
                headers=headers,
                timeout=self.timeout
            )

            logger.info(
                f"[{trace_id}] Webhook response: status={response.status_code} "
                f"webhook_id={webhook.id}"
            )

            # Determine delivery status
            status = (
                WebhookDeliveryStatus.SENT.value
                if response.status_code < 400
                else WebhookDeliveryStatus.FAILED.value
            )

            # Create delivery record
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_type=event_value,
                payload=payload_dict,
                status=status,
                response_status=response.status_code,
                error_message=response.text if response.status_code >= 400 else None,
                retry_count=0,
                last_attempt_at=datetime.utcnow()
            )

            # Handle retries for failed deliveries
            if response.status_code >= 400:
                if delivery.retry_count < self.max_retries:
                    delivery.status = WebhookDeliveryStatus.RETRYING.value
                    delivery.retry_count = 1
                    logger.warning(
                        f"[{trace_id}] Webhook delivery failed, scheduling retry "
                        f"(attempt {delivery.retry_count}/{self.max_retries}): "
                        f"webhook={webhook.id}, event={event_value}, "
                        f"status={response.status_code}, error={response.text[:200]}"
                    )
                    self._schedule_retry(delivery)
                else:
                    logger.error(
                        f"[{trace_id}] Webhook delivery failed after "
                        f"{self.max_retries} retries: webhook={webhook.id}, "
                        f"event={event_value}"
                    )
                    self._notify_webhook_failure(webhook, payload, response.text[:200])
            else:
                webhook.last_delivered_at = datetime.utcnow()

            db.session.add(delivery)
            db.session.commit()

            return response.status_code < 400

        except requests.exceptions.Timeout as e:
            logger.error(
                f"[{trace_id}] Webhook request timed out: webhook={webhook.id}, "
                f"url={webhook.url}, error={str(e)}"
            )
            return self._handle_delivery_error(
                webhook, payload, f"Timeout: {str(e)}"
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"[{trace_id}] Webhook connection error: webhook={webhook.id}, "
                f"url={webhook.url}, error={str(e)}"
            )
            return self._handle_delivery_error(
                webhook, payload, f"Connection error: {str(e)}"
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"[{trace_id}] Webhook request failed: webhook={webhook.id}, "
                f"error={str(e)}",
                exc_info=True
            )
            return self._handle_delivery_error(
                webhook, payload, f"Request failed: {str(e)}"
            )
        except Exception as e:
            logger.error(
                f"[{trace_id}] Unexpected error delivering webhook: {e}",
                exc_info=True
            )
            try:
                db.session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error rolling back session: {rollback_error}", exc_info=True)
            return False
        finally:
            # Ensure connection is properly closed
            if response is not None:
                try:
                    response.close()
                except Exception as e:
                    logger.error(f"Error closing response: {e}", exc_info=True)

    def _handle_delivery_error(
        self,
        webhook: Webhook,
        payload: WebhookPayload,
        error_message: str
    ) -> bool:
        """Handle webhook delivery errors with retry logic"""
        trace_id = payload.trace_id or "unknown"
        event_value = payload.event_type.value

        # Create failed delivery record
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event_type=event_value,
            payload={
                "event_type": event_value,
                "data": payload.data,
                "timestamp": payload.timestamp,
                "idempotency_key": payload.idempotency_key,
            },
            status=WebhookDeliveryStatus.FAILED.value,
            error_message=error_message,
            retry_count=1,
            last_attempt_at=datetime.utcnow()
        )

        if delivery.retry_count < self.max_retries:
            delivery.status = WebhookDeliveryStatus.RETRYING.value
            delivery.retry_count = 1
            self._schedule_retry(delivery)
        else:
            # Log alert for persistent failures
            logger.error(
                f"[{trace_id}] Webhook delivery failed after {self.max_retries} retries: "
                f"webhook={webhook.id}, url={webhook.url}, event={event_value}, "
                f"error={error_message}"
            )
            self._notify_webhook_failure(webhook, payload, error_message)

        db.session.add(delivery)
        db.session.commit()

        return False

    def _notify_webhook_failure(self, webhook: Webhook, payload: WebhookPayload, error_message: str):
        """Notify admins about webhook failures"""
        try:
            # Use email or other notification system
            # Example with email
            if current_app.config.get('WEBHOOK_FAILURE_NOTIFICATION_EMAIL'):
                # Implement email sending logic here
                pass
            
            # Or use alerting system like Sentry, PagerDuty, etc.
            if current_app.config.get('WEBHOOK_FAILURE_ALERT_WEBHOOK'):
                # Send to external alerting system
                pass
                
        except Exception as e:
            logger.error(f"Failed to send webhook failure notification: {e}", exc_info=True)

    def _schedule_retry(self, delivery: WebhookDelivery) -> None:
        """Schedule a retry for failed webhook delivery"""
        try:
            # Import here to avoid circular dependency
            from ..tasks import retry_webhook_delivery
            
            retry_webhook_delivery.apply_async(
                args=[delivery.id],
                countdown=self.retry_delay * delivery.retry_count,
                retry=True,
                retry_policy={
                    'max_retries': self.max_retries - delivery.retry_count,
                    'interval_start': self.retry_delay,
                    'interval_step': self.retry_delay,
                    'interval_max': self.max_retry_delay,
                }
            )
            logger.info(
                f"Webhook retry scheduled: webhook={delivery.webhook_id}, "
                f"event={delivery.event_type}, attempt={delivery.retry_count}"
            )
        except Exception as e:
            logger.error(f"Failed to schedule retry: {e}", exc_info=True)

    def _serialize_payload(self, payload_dict: Dict[str, Any]) -> str:
        """Serialize payload to JSON string"""
        try:
            return json.dumps(payload_dict, sort_keys=True, default=str)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize payload: {e}", exc_info=True)
            # Return minimal payload for error case
            return json.dumps({
                "event_type": payload_dict.get("event_type"),
                "error": "Payload serialization failed",
                "timestamp": payload_dict.get("timestamp")
            }, sort_keys=True, default=str)

    def _emit_expense(
        self,
        event_type: WebhookEventType,
        expense: Any
    ) -> bool:
        """Emit expense webhook (common method for created/updated events)"""
        data = {
            "id": expense.id,
            "amount": float(expense.amount),
            "currency": expense.currency,
            "expense_type": expense.expense_type,
            "description": expense.notes or "",
            "date": expense.spent_at.isoformat(),
            "category_id": expense.category_id,
        }
        payload = self._build_payload(event_type, data, expense.user_id)
        return self._deliver_webhook(payload)

    def emit_expense_created(self, expense: Any) -> bool:
        """Emit webhook when expense is created"""
        return self._emit_expense(WebhookEventType.EXPENSE_CREATED, expense)

    def emit_expense_updated(self, expense: Any) -> bool:
        """Emit webhook when expense is updated"""
        return self._emit_expense(WebhookEventType.EXPENSE_UPDATED, expense)

    def emit_expense_deleted(self, expense_id: int, user_id: int) -> bool:
        """Emit webhook when expense is deleted"""
        data = {
            "expense_id": expense_id,
        }
        payload = self._build_payload(WebhookEventType.EXPENSE_DELETED, data, user_id)
        return self._deliver_webhook(payload)

    def _emit_bill(
        self,
        event_type: WebhookEventType,
        bill: Any
    ) -> bool:
        """Emit bill webhook (common method for created/updated events)"""
        data = {
            "id": bill.id,
            "name": bill.name,
            "amount": float(bill.amount),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat(),
            "cadence": bill.cadence.value,
            "autopay_enabled": bill.autopay_enabled,
            "channel_whatsapp": bill.channel_whatsapp,
            "channel_email": bill.channel_email,
        }
        payload = self._build_payload(event_type, data, bill.user_id)
        return self._deliver_webhook(payload)

    def emit_bill_created(self, bill: Any) -> bool:
        """Emit webhook when bill is created"""
        return self._emit_bill(WebhookEventType.BILL_CREATED, bill)

    def emit_bill_updated(self, bill: Any) -> bool:
        """Emit webhook when bill is updated"""
        return self._emit_bill(WebhookEventType.BILL_UPDATED, bill)

    def emit_bill_paid(self, bill_id: int, user_id: int) -> bool:
        """Emit webhook when bill is marked as paid"""
        data = {
            "bill_id": bill_id,
        }
        payload = self._build_payload(WebhookEventType.BILL_PAID, data, user_id)
        return self._deliver_webhook(payload)

    def emit_user_registered(self, user: Any) -> bool:
        """Emit webhook when user is registered"""
        data = {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
        }
        payload = self._build_payload(WebhookEventType.USER_REGISTERED, data, user.id)
        return self._deliver_webhook(payload)

    def emit_reminder_triggered(self, reminder: Any) -> bool:
        """Emit webhook when reminder is triggered"""
        bill_name = reminder.bill.name if reminder.bill else None
        data = {
            "id": reminder.id,
            "bill_id": reminder.bill_id,
            "bill_name": bill_name,
            "message": reminder.message,
            "send_at": reminder.send_at.isoformat(),
            "sent": reminder.sent,
            "channel": reminder.channel,
        }
        payload = self._build_payload(WebhookEventType.REMINDER_TRIGGERED, data, reminder.user_id)
        return self._deliver_webhook(payload)


# Global webhook service instance
webhook_service = WebhookService()
