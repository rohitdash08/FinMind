"""
Webhook Service for FinMind

Provides signed webhook delivery with retry logic and failure handling.
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import requests

from ..config import Settings

logger = logging.getLogger("finmind.webhooks")

# Event types supported by the webhook system
class WebhookEventType(str, Enum):
    # Expense events
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_DELETED = "expense.deleted"

    # Bill events
    BILL_CREATED = "bill.created"
    BILL_UPDATED = "bill.updated"
    BILL_DELETED = "bill.deleted"
    BILL_DUE_SOON = "bill.due_soon"
    BILL_OVERDUE = "bill.overdue"

    # Category events
    CATEGORY_CREATED = "category.created"
    CATEGORY_UPDATED = "category.updated"
    CATEGORY_DELETED = "category.deleted"

    # Reminder events
    REMINDER_SENT = "reminder.sent"

    # User events
    USER_CREATED = "user.created"


class WebhookDelivery:
    """Represents a webhook delivery attempt."""

    def __init__(
        self,
        event_type: str,
        payload: dict,
        webhook_url: str,
        secret: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.event_type = event_type
        self.payload = payload
        self.webhook_url = webhook_url
        self.secret = secret
        self.timeout = timeout
        self.max_retries = max_retries
        self.delivery_id: str | None = None
        self.successful = False
        self.response_status: int | None = None
        self.response_body: str | None = None
        self.attempts = 0
        self.error: str | None = None

    def _generate_signature(self, payload: str) -> str | None:
        """Generate HMAC-SHA256 signature for the payload."""
        if not self.secret:
            return None
        signature = hmac.new(
            self.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"

    def _generate_payload(self) -> dict:
        """Generate the webhook payload with metadata."""
        now = datetime.now(timezone.utc).isoformat()
        self.delivery_id = hashlib.sha256(
            f"{now}{self.event_type}".encode()
        ).hexdigest()[:16]

        return {
            "id": self.delivery_id,
            "type": self.event_type,
            "timestamp": now,
            "data": self.payload,
        }

    def deliver(self) -> bool:
        """
        Attempt to deliver the webhook with retries.
        Returns True if delivery was successful.
        """
        payload_dict = self._generate_payload()
        payload_str = json.dumps(payload_dict, default=str)
        signature = self._generate_signature(payload_str)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "FinMind-Webhook/1.0",
        }
        if signature:
            headers["X-Webhook-Signature"] = signature

        for attempt in range(1, self.max_retries + 1):
            self.attempts = attempt
            try:
                logger.info(
                    "Delivering webhook event=%s attempt=%d/%d url=%s",
                    self.event_type,
                    attempt,
                    self.max_retries,
                    self.webhook_url,
                )

                response = requests.post(
                    self.webhook_url,
                    data=payload_str,
                    headers=headers,
                    timeout=self.timeout,
                )

                self.response_status = response.status_code
                self.response_body = response.text[:500] if response.text else None

                if 200 <= response.status_code < 300:
                    self.successful = True
                    logger.info(
                        "Webhook delivered successfully event=%s delivery_id=%s status=%d",
                        self.event_type,
                        self.delivery_id,
                        response.status_code,
                    )
                    return True
                else:
                    logger.warning(
                        "Webhook delivery failed event=%s attempt=%d status=%d",
                        self.event_type,
                        attempt,
                        response.status_code,
                    )

            except requests.exceptions.Timeout:
                self.error = "Request timeout"
                logger.warning(
                    "Webhook timeout event=%s attempt=%d", self.event_type, attempt
                )
            except requests.exceptions.ConnectionError as e:
                self.error = f"Connection error: {str(e)[:100]}"
                logger.warning(
                    "Webhook connection error event=%s attempt=%d error=%s",
                    self.event_type,
                    attempt,
                    str(e)[:100],
                )
            except Exception as e:
                self.error = str(e)[:200]
                logger.exception(
                    "Webhook delivery exception event=%s attempt=%d", self.event_type, attempt
                )

            # Wait before retry (exponential backoff)
            if attempt < self.max_retries:
                wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s...
                time.sleep(wait_time)

        logger.error(
            "Webhook delivery failed permanently event=%s attempts=%d",
            self.event_type,
            self.attempts,
        )
        return False


class WebhookManager:
    """
    Manages webhook deliveries asynchronously.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._enabled = bool(settings.webhook_url)

    @property
    def enabled(self) -> bool:
        """Check if webhooks are enabled."""
        return self._enabled

    def emit(self, event_type: WebhookEventType, data: dict) -> None:
        """
        Emit a webhook event asynchronously.
        This method returns immediately; delivery happens in background.
        """
        if not self.enabled:
            logger.debug("Webhooks disabled, skipping event %s", event_type)
            return

        # Run delivery in background thread
        thread = threading.Thread(
            target=self._deliver_async,
            args=(event_type, data),
            daemon=True,
        )
        thread.start()

    def _deliver_async(self, event_type: WebhookEventType, data: dict) -> None:
        """Deliver webhook in background thread."""
        delivery = WebhookDelivery(
            event_type=event_type.value,
            payload=data,
            webhook_url=self.settings.webhook_url,
            secret=self.settings.webhook_secret,
            timeout=self.settings.webhook_timeout,
            max_retries=self.settings.webhook_max_retries,
        )
        delivery.deliver()


# Global webhook manager instance (initialized lazily)
_webhook_manager: WebhookManager | None = None


def get_webhook_manager() -> WebhookManager:
    """Get or create the global webhook manager."""
    global _webhook_manager
    if _webhook_manager is None:
        from flask import current_app

        settings = current_app.config.get("SETTINGS", Settings())
        _webhook_manager = WebhookManager(settings)
    return _webhook_manager


def emit_webhook(event_type: WebhookEventType, data: dict) -> None:
    """
    Convenience function to emit a webhook event.
    """
    manager = get_webhook_manager()
    manager.emit(event_type, data)
