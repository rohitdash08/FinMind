"""Comprehensive tests for the FinMind webhook event system."""

from __future__ import annotations

import asyncio
import json
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webhook.events import EventType, TRANSACTION_EVENTS, ACCOUNT_EVENTS, ALL_EVENTS
from webhook.models import DeliveryStatus, WebhookDelivery, WebhookEndpoint, WebhookEvent
from webhook.signer import WebhookSigner
from webhook.dispatcher import WebhookDispatcher
from webhook.registry import WebhookRegistry
from webhook.middleware import WebhookManager


# ======================================================================
# Event types
# ======================================================================

class TestEventTypes:
    def test_all_event_values(self):
        expected = {
            "transaction.created", "transaction.updated", "transaction.deleted",
            "account.connected", "account.disconnected", "account.synced",
            "budget.exceeded", "budget.warning",
            "anomaly.detected",
            "export.completed",
        }
        assert {e.value for e in EventType} == expected

    def test_event_groups(self):
        assert len(TRANSACTION_EVENTS) == 3
        assert len(ACCOUNT_EVENTS) == 3
        assert len(ALL_EVENTS) == 10

    def test_event_is_string(self):
        assert EventType.TRANSACTION_CREATED == "transaction.created"
        assert isinstance(EventType.BUDGET_EXCEEDED, str)


# ======================================================================
# Models
# ======================================================================

class TestModels:
    def test_endpoint_defaults(self):
        ep = WebhookEndpoint(url="https://example.com/hook", secret="s3cret")
        assert ep.is_active is True
        assert ep.events == set()
        assert ep.id  # auto-generated

    def test_event_defaults(self):
        ev = WebhookEvent(event_type="transaction.created", payload={"amount": 10})
        assert ev.id
        assert ev.payload == {"amount": 10}

    def test_delivery_defaults(self):
        d = WebhookDelivery(event_id="e1", endpoint_id="ep1")
        assert d.status == DeliveryStatus.PENDING
        assert d.attempts == 0
        assert d.max_retries == 5


# ======================================================================
# Signer
# ======================================================================

class TestSigner:
    def test_sign_produces_sha256_prefix(self):
        signer = WebhookSigner("mysecret")
        sig = signer.sign({"hello": "world"})
        assert sig.startswith("sha256=")

    def test_verify_valid(self):
        signer = WebhookSigner("mysecret")
        payload = {"key": "value", "num": 42}
        sig = signer.sign(payload)
        assert signer.verify(payload, sig) is True

    def test_verify_invalid(self):
        signer = WebhookSigner("mysecret")
        payload = {"key": "value"}
        assert signer.verify(payload, "sha256=bad") is False

    def test_sign_with_timestamp(self):
        signer = WebhookSigner("secret")
        ts = "2026-01-01T00:00:00+00:00"
        sig1 = signer.sign({"a": 1}, timestamp=ts)
        sig2 = signer.sign({"a": 1}, timestamp=ts)
        assert sig1 == sig2

    def test_different_timestamps_different_sigs(self):
        signer = WebhookSigner("secret")
        sig1 = signer.sign({"a": 1}, timestamp="t1")
        sig2 = signer.sign({"a": 1}, timestamp="t2")
        assert sig1 != sig2

    def test_different_secrets_different_sigs(self):
        sig1 = WebhookSigner("secret_a").sign({"x": 1})
        sig2 = WebhookSigner("secret_b").sign({"x": 1})
        assert sig1 != sig2

    def test_empty_secret_raises(self):
        with pytest.raises(ValueError):
            WebhookSigner("")

    def test_manual_hmac_matches(self):
        secret = "test_secret"
        payload = {"id": "123"}
        signer = WebhookSigner(secret)
        sig = signer.sign(payload)

        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        expected = "sha256=" + hmac.new(
            secret.encode(), raw, hashlib.sha256
        ).hexdigest()
        assert sig == expected


# ======================================================================
# Registry
# ======================================================================

class TestRegistry:
    def test_register_and_get(self):
        reg = WebhookRegistry()
        ep = reg.register("https://example.com/hook", "sec")
        assert reg.get(ep.id) is ep

    def test_list_all(self):
        reg = WebhookRegistry()
        reg.register("https://a.com", "s1")
        reg.register("https://b.com", "s2")
        assert len(reg.list_all()) == 2

    def test_delete(self):
        reg = WebhookRegistry()
        ep = reg.register("https://a.com", "s")
        assert reg.delete(ep.id) is True
        assert reg.get(ep.id) is None
        assert reg.delete("nonexistent") is False

    def test_update(self):
        reg = WebhookRegistry()
        ep = reg.register("https://a.com", "s")
        updated = reg.update(ep.id, is_active=False, description="disabled")
        assert updated is not None
        assert updated.is_active is False
        assert updated.description == "disabled"

    def test_update_nonexistent(self):
        reg = WebhookRegistry()
        assert reg.update("nope", is_active=False) is None

    def test_list_for_event_filters(self):
        reg = WebhookRegistry()
        reg.register("https://a.com", "s", events={"transaction.created"})
        reg.register("https://b.com", "s", events={"account.connected"})
        reg.register("https://c.com", "s", events=set())  # wildcard

        matches = reg.list_for_event("transaction.created")
        urls = {str(ep.url) for ep in matches}
        assert "https://a.com/" in urls or "https://a.com" in urls
        assert "https://c.com/" in urls or "https://c.com" in urls
        assert len(matches) == 2

    def test_inactive_excluded(self):
        reg = WebhookRegistry()
        ep = reg.register("https://a.com", "s", events={"transaction.created"})
        reg.update(ep.id, is_active=False)
        assert reg.list_for_event("transaction.created") == []


# ======================================================================
# Dispatcher
# ======================================================================

class TestDispatcher:
    @pytest.mark.asyncio
    async def test_successful_delivery(self):
        dispatcher = WebhookDispatcher(max_retries=3, base_backoff=0.001)
        event = WebhookEvent(event_type="transaction.created", payload={"id": "t1"})
        endpoint = WebhookEndpoint(url="https://example.com/hook", secret="sec")

        with patch.object(dispatcher, "_post", new_callable=AsyncMock, return_value=200):
            delivery = await dispatcher.dispatch(event, endpoint)

        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 1
        assert delivery.last_response_code == 200
        assert delivery.delivered_at is not None

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        dispatcher = WebhookDispatcher(max_retries=3, base_backoff=0.001)
        event = WebhookEvent(event_type="transaction.created", payload={})
        endpoint = WebhookEndpoint(url="https://example.com/hook", secret="sec")

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return 500
            return 200

        with patch.object(dispatcher, "_post", side_effect=mock_post):
            delivery = await dispatcher.dispatch(event, endpoint)

        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        dispatcher = WebhookDispatcher(max_retries=2, base_backoff=0.001)
        event = WebhookEvent(event_type="transaction.created", payload={})
        endpoint = WebhookEndpoint(url="https://example.com/hook", secret="sec")

        with patch.object(dispatcher, "_post", new_callable=AsyncMock, return_value=500):
            delivery = await dispatcher.dispatch(event, endpoint)

        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 3  # initial + 2 retries
        assert delivery.last_response_code == 500

    @pytest.mark.asyncio
    async def test_exception_triggers_retry(self):
        dispatcher = WebhookDispatcher(max_retries=1, base_backoff=0.001)
        event = WebhookEvent(event_type="anomaly.detected", payload={})
        endpoint = WebhookEndpoint(url="https://example.com/hook", secret="sec")

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("refused")
            return 200

        with patch.object(dispatcher, "_post", side_effect=mock_post):
            delivery = await dispatcher.dispatch(event, endpoint)

        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 2
        assert delivery.last_error == "refused"

    @pytest.mark.asyncio
    async def test_dispatch_to_many(self):
        dispatcher = WebhookDispatcher(max_retries=0, base_backoff=0.001)
        event = WebhookEvent(event_type="export.completed", payload={})
        ep1 = WebhookEndpoint(url="https://a.com/hook", secret="s1")
        ep2 = WebhookEndpoint(url="https://b.com/hook", secret="s2")

        with patch.object(dispatcher, "_post", new_callable=AsyncMock, return_value=200):
            deliveries = await dispatcher.dispatch_to_many(event, [ep1, ep2])

        assert len(deliveries) == 2
        assert all(d.status == DeliveryStatus.DELIVERED for d in deliveries)

    @pytest.mark.asyncio
    async def test_get_delivery(self):
        dispatcher = WebhookDispatcher(max_retries=0, base_backoff=0.001)
        event = WebhookEvent(event_type="budget.exceeded", payload={})
        endpoint = WebhookEndpoint(url="https://example.com/hook", secret="sec")

        with patch.object(dispatcher, "_post", new_callable=AsyncMock, return_value=200):
            delivery = await dispatcher.dispatch(event, endpoint)

        assert dispatcher.get_delivery(delivery.id) is delivery
        assert dispatcher.get_delivery("nonexistent") is None


# ======================================================================
# WebhookManager (middleware)
# ======================================================================

class TestWebhookManager:
    @pytest.mark.asyncio
    async def test_emit_delivers(self):
        manager = WebhookManager()
        manager.register_endpoint(
            url="https://example.com/hook",
            secret="sec",
            events={"transaction.created"},
        )

        with patch.object(
            manager.dispatcher, "_post", new_callable=AsyncMock, return_value=200
        ):
            ids = await manager.emit("transaction.created", {"id": "t1"})

        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_emit_no_matching_endpoints(self):
        manager = WebhookManager()
        manager.register_endpoint(
            url="https://example.com/hook",
            secret="sec",
            events={"account.connected"},
        )
        ids = await manager.emit("transaction.created", {})
        assert ids == []

    def test_register_returns_id(self):
        manager = WebhookManager()
        eid = manager.register_endpoint("https://a.com", "s")
        assert isinstance(eid, str)
        assert len(eid) > 0
