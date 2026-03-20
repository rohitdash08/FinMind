from .client import WebhookClient
import hashlib
import hmac
import json
import logging
import time
from typing import Dict, Any, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class WebhookClient:
    """
    A client for emitting signed webhooks with retry & failure handling.
    """

    def __init__(
        self,
        secret: str,
        timeout: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 0.3,
    ):
        """
        Args:
            secret: Shared secret used to sign the payload.
            timeout: HTTP timeout in seconds.
            max_retries: Max number of retries on failure.
            backoff_factor: Backoff multiplier between retries.
        """
        self.secret = secret.encode()
        self.timeout = timeout

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """
        Sign the payload using HMAC-SHA256.
        """
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(
            self.secret, payload_str.encode(), hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def send(
        self,
        url: str,
        event_type: str,
        data: Dict[str, Any],
        idempotency_key: str = None,
    ) -> requests.Response:
        """
        Send a signed webhook.

        Args:
            url: Webhook endpoint URL.
            event_type: Type of the event (e.g., 'order.created').
            data: Event payload.
            idempotency_key: Optional unique key to prevent duplicates.

        Returns:
            Response object.
        """
        payload = {
            "id": idempotency_key or str(int(time.time() * 1000)),
            "type": event_type,
            "timestamp": int(time.time()),
            "data": data,
        }
        signature = self._sign_payload(payload)
        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Signature": signature,
            "User-Agent": "FinMind-Webhook/1.0",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        logger.info(f"Sending webhook to {url} with event {event_type}")
        response = self.session.post(
            url, data=json.dumps(payload), headers=headers, timeout=self.timeout
        )
        response.raise_for_status()
        return response


class WebhookEmitter:
    """
    High-level emitter that can broadcast events to multiple URLs.
    """

    def __init__(self, secret: str, urls: List[str]):
        self.client = WebhookClient(secret)
        self.urls = urls

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Emit an event to all configured URLs.
        """
        for url in self.urls:
            try:
                self.client.send(url, event_type, data)
            except Exception as e:
                logger.error(
                    f"Failed to deliver webhook to {url} for event {event_type}: {e}"
                )
# FinMind Webhook Event Types

This document lists all event types emitted by FinMind webhooks.

## Event Payload Structure

All events share the following envelope:

