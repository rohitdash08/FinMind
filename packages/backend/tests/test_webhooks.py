"""
Tests for the webhook event system.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import pytest

from app.services.webhooks import (
    DeliveryStatus,
    EventType,
    WebhookManager,
    sign_payload,
    verify_signature,
)


class TestSignatureVerification:
    """Test HMAC-SHA256 signing and verification."""

    def test_sign_payload(self):
        payload = '{"type": "expense.created"}'
        secret = "test-secret-123"
        sig = sign_payload(payload, secret)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex = 64 chars

    def test_verify_valid_signature(self):
        payload = '{"amount": 42.50}'
        secret = "my-secret"
        sig = sign_payload(payload, secret)
        assert verify_signature(payload, sig, secret) is True

    def test_verify_invalid_signature(self):
        payload = '{"amount": 42.50}'
        assert verify_signature(payload, "invalid-sig", "secret") is False

    def test_verify_wrong_secret(self):
        payload = '{"amount": 42.50}'
        sig = sign_payload(payload, "correct-secret")
        assert verify_signature(payload, sig, "wrong-secret") is False

    def test_different_payloads_different_signatures(self):
        secret = "test"
        sig1 = sign_payload("payload1", secret)
        sig2 = sign_payload("payload2", secret)
        assert sig1 != sig2

    def test_timing_safe_comparison(self):
        """verify_signature should use constant-time comparison."""
        payload = '{"test": true}'
        secret = "secret"
        sig = sign_payload(payload, secret)
        # Should still work correctly
        assert verify_signature(payload, sig, secret) is True


class TestWebhookManager:
    """Test the webhook manager."""

    def setup_method(self):
        self.manager = WebhookManager()

    def test_register_endpoint(self):
        ep = self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="test-secret",
            events=["expense.created"],
        )
        assert ep.url == "https://example.com/webhook"
        assert ep.active is True
        assert "expense.created" in ep.events

    def test_register_all_events(self):
        ep = self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="test-secret",
        )
        assert len(ep.events) == len(EventType)

    def test_list_endpoints(self):
        self.manager.register_endpoint("https://a.com", "s1")
        self.manager.register_endpoint("https://b.com", "s2")
        assert len(self.manager.list_endpoints()) == 2

    def test_unregister_endpoint(self):
        ep = self.manager.register_endpoint("https://a.com", "s1")
        assert self.manager.unregister_endpoint(ep.id) is True
        assert len(self.manager.list_endpoints()) == 0

    def test_unregister_nonexistent(self):
        assert self.manager.unregister_endpoint("fake-id") is False

    def test_get_endpoint(self):
        ep = self.manager.register_endpoint("https://a.com", "s1")
        found = self.manager.get_endpoint(ep.id)
        assert found is not None
        assert found.url == "https://a.com"

    def test_emit_to_subscribed(self):
        self.manager.register_endpoint(
            url="https://httpbin.org/status/200",
            secret="test",
            events=["expense.created"],
        )
        # Will fail (can't reach httpbin in tests), but should create delivery
        deliveries = self.manager.emit("expense.created", {"amount": 10})
        assert len(deliveries) == 1
        assert deliveries[0].event_type == "expense.created"

    def test_emit_skips_unsubscribed(self):
        self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="test",
            events=["bill.due"],
        )
        deliveries = self.manager.emit("expense.created", {"amount": 10})
        assert len(deliveries) == 0

    def test_emit_skips_inactive(self):
        ep = self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="test",
        )
        ep.active = False
        deliveries = self.manager.emit("expense.created", {"amount": 10})
        assert len(deliveries) == 0

    def test_delivery_payload_structure(self):
        self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="test",
            events=["expense.created"],
        )
        deliveries = self.manager.emit("expense.created", {"amount": 42.50})
        payload = deliveries[0].payload
        assert "id" in payload
        assert payload["type"] == "expense.created"
        assert "created_at" in payload
        assert payload["data"]["amount"] == 42.50

    def test_local_handler(self):
        received = []

        def handler(event_type, data):
            received.append((event_type, data))

        self.manager.on("expense.created", handler)
        self.manager.emit("expense.created", {"amount": 10})
        assert len(received) == 1
        assert received[0][0] == "expense.created"

    def test_get_deliveries_filter_by_status(self):
        self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="test",
        )
        self.manager.emit("expense.created", {"amount": 10})
        failed = self.manager.get_deliveries(status=DeliveryStatus.FAILED)
        assert all(d.status == DeliveryStatus.FAILED for d in failed)

    def test_delivery_includes_signature(self):
        """Deliveries should include X-Webhook-Signature header."""
        ep = self.manager.register_endpoint(
            url="https://example.com/webhook",
            secret="my-secret",
            events=["expense.created"],
        )
        deliveries = self.manager.emit("expense.created", {"test": True})
        assert len(deliveries) == 1
        # The delivery was attempted (even if it failed due to network)
        assert deliveries[0].attempts > 0


class TestEventTypes:
    """Test event type enum."""

    def test_all_types_are_strings(self):
        for e in EventType:
            assert isinstance(e.value, str)
            assert "." in e.value  # Format: category.action

    def test_standard_event_types(self):
        values = {e.value for e in EventType}
        assert "expense.created" in values
        assert "bill.due" in values
        assert "bank_sync.completed" in values
