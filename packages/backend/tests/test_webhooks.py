"""Tests for the Webhook Event System."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.webhooks import (
    WebhookDelivery,
    WebhookEventType,
    WebhookManager,
    WebhookRegistration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = "ok"
    return resp


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_with_defaults(self):
        mgr = WebhookManager()
        reg = mgr.register_webhook("https://example.com/hook")
        assert isinstance(reg, WebhookRegistration)
        assert reg.url == "https://example.com/hook"
        assert set(reg.events) == {e.value for e in WebhookEventType}
        assert reg.active is True
        assert len(reg.secret) > 0

    def test_register_specific_events(self):
        mgr = WebhookManager()
        reg = mgr.register_webhook(
            "https://example.com/hook",
            events=["trade_signal", "risk_alert"],
        )
        assert reg.events == ["trade_signal", "risk_alert"]

    def test_register_rejects_empty_url(self):
        mgr = WebhookManager()
        with pytest.raises(ValueError, match="must not be empty"):
            mgr.register_webhook("")

    def test_register_rejects_unknown_event(self):
        mgr = WebhookManager()
        with pytest.raises(ValueError, match="Unknown event types"):
            mgr.register_webhook("https://example.com/hook", events=["nonexistent"])

    def test_unregister(self):
        mgr = WebhookManager()
        reg = mgr.register_webhook("https://example.com/hook")
        assert mgr.unregister_webhook(reg.id) is True
        assert mgr.unregister_webhook(reg.id) is False

    def test_list_webhooks(self):
        mgr = WebhookManager()
        mgr.register_webhook("https://a.com")
        mgr.register_webhook("https://b.com")
        assert len(mgr.list_webhooks()) == 2

    def test_get_webhook(self):
        mgr = WebhookManager()
        reg = mgr.register_webhook("https://example.com/hook")
        assert mgr.get_webhook(reg.id) is reg
        assert mgr.get_webhook("nonexistent") is None


# ---------------------------------------------------------------------------
# Trigger / delivery tests
# ---------------------------------------------------------------------------

class TestTriggerEvent:
    @patch("app.services.webhooks.requests.post")
    def test_trigger_delivers_to_matching_webhook(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook", events=["trade_signal"])
        deliveries = mgr.trigger_event("trade_signal", {"symbol": "AAPL"})
        assert len(deliveries) == 1
        assert deliveries[0].success is True
        assert deliveries[0].status_code == 200
        mock_post.assert_called_once()

    @patch("app.services.webhooks.requests.post")
    def test_trigger_skips_non_matching_webhook(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook", events=["risk_alert"])
        deliveries = mgr.trigger_event("trade_signal")
        assert len(deliveries) == 0
        mock_post.assert_not_called()

    def test_trigger_rejects_unknown_event_type(self):
        mgr = WebhookManager()
        with pytest.raises(ValueError, match="Unknown event type"):
            mgr.trigger_event("unknown_event")

    @patch("app.services.webhooks.requests.post")
    def test_trigger_all_event_types(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook")  # all events
        for event_type in WebhookEventType:
            deliveries = mgr.trigger_event(event_type.value, {"test": True})
            assert len(deliveries) == 1
            assert deliveries[0].success is True

    @patch("app.services.webhooks.requests.post")
    def test_trigger_skips_inactive_webhook(self, mock_post):
        mgr = WebhookManager()
        reg = mgr.register_webhook("https://example.com/hook", events=["trade_signal"])
        reg.active = False
        deliveries = mgr.trigger_event("trade_signal")
        assert len(deliveries) == 0
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Retry tests
# ---------------------------------------------------------------------------

class TestRetry:
    @patch("app.services.webhooks.requests.post")
    @patch("app.services.webhooks.time.sleep")
    def test_retry_on_server_error(self, mock_sleep, mock_post):
        mock_post.side_effect = [
            _mock_response(500),
            _mock_response(500),
            _mock_response(200),
        ]
        mgr = WebhookManager(max_retries=3, base_delay=1.0)
        mgr.register_webhook("https://example.com/hook", events=["trade_signal"])
        deliveries = mgr.trigger_event("trade_signal")
        assert len(deliveries) == 1
        assert deliveries[0].success is True
        assert deliveries[0].attempts == 3
        assert mock_post.call_count == 3

    @patch("app.services.webhooks.requests.post")
    @patch("app.services.webhooks.time.sleep")
    def test_retry_exhausted(self, mock_sleep, mock_post):
        mock_post.return_value = _mock_response(500)
        mgr = WebhookManager(max_retries=3, base_delay=0.1)
        mgr.register_webhook("https://example.com/hook", events=["risk_alert"])
        deliveries = mgr.trigger_event("risk_alert")
        assert len(deliveries) == 1
        assert deliveries[0].success is False
        assert deliveries[0].attempts == 3
        assert deliveries[0].error == "HTTP 500"
        assert mock_post.call_count == 3

    @patch("app.services.webhooks.requests.post")
    @patch("app.services.webhooks.time.sleep")
    def test_retry_on_connection_error(self, mock_sleep, mock_post):
        mock_post.side_effect = requests.ConnectionError("refused")
        mgr = WebhookManager(max_retries=2, base_delay=0.1)
        mgr.register_webhook("https://example.com/hook", events=["market_anomaly"])
        deliveries = mgr.trigger_event("market_anomaly")
        assert len(deliveries) == 1
        assert deliveries[0].success is False
        assert deliveries[0].attempts == 2

    @patch("app.services.webhooks.requests.post")
    @patch("app.services.webhooks.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep, mock_post):
        mock_post.side_effect = [
            _mock_response(500),
            _mock_response(500),
            _mock_response(200),
        ]
        mgr = WebhookManager(max_retries=3, base_delay=2.0, max_delay=30.0)
        mgr.register_webhook("https://example.com/hook", events=["trade_signal"])
        mgr.trigger_event("trade_signal")
        # delays: 2^0*2=2, 2^1*2=4
        calls = mock_sleep.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == pytest.approx(2.0)
        assert calls[1][0][0] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Signature tests
# ---------------------------------------------------------------------------

class TestSignature:
    def test_sign_and_verify(self):
        mgr = WebhookManager()
        body = '{"test": true}'
        secret = "mysecret"
        sig = mgr._sign(secret, body)
        assert mgr.verify_signature(secret, body, sig) is True
        assert mgr.verify_signature("wrong", body, sig) is False

    @patch("app.services.webhooks.requests.post")
    def test_signature_sent_in_header(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook(
            "https://example.com/hook",
            events=["trade_signal"],
            secret="testsecret",
        )
        mgr.trigger_event("trade_signal", {"symbol": "AAPL"})

        call_kwargs = mock_post.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs.kwargs["headers"]
        assert "X-FinMind-Signature" in headers
        body = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs.kwargs["data"]
        assert mgr.verify_signature("testsecret", body, headers["X-FinMind-Signature"])


# ---------------------------------------------------------------------------
# Delivery history tests
# ---------------------------------------------------------------------------

class TestDeliveryHistory:
    @patch("app.services.webhooks.requests.post")
    def test_get_deliveries(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook", events=["trade_signal"])
        mgr.trigger_event("trade_signal")
        assert len(mgr.get_deliveries()) == 1

    @patch("app.services.webhooks.requests.post")
    def test_filter_deliveries_by_webhook(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        reg1 = mgr.register_webhook("https://a.com", events=["trade_signal"])
        mgr.register_webhook("https://b.com", events=["trade_signal"])
        mgr.trigger_event("trade_signal")
        assert len(mgr.get_deliveries(webhook_id=reg1.id)) == 1

    @patch("app.services.webhooks.requests.post")
    def test_filter_deliveries_by_event(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook")
        mgr.trigger_event("trade_signal")
        mgr.trigger_event("risk_alert")
        assert len(mgr.get_deliveries(event_type="trade_signal")) == 1
        assert len(mgr.get_deliveries(event_type="risk_alert")) == 1

    def test_clear_deliveries(self):
        mgr = WebhookManager()
        mgr._deliveries.append(
            WebhookDelivery(
                id="test", webhook_id="w1", event_type="test", payload={}
            )
        )
        mgr.clear_deliveries()
        assert len(mgr.get_deliveries()) == 0


# ---------------------------------------------------------------------------
# Payload structure tests
# ---------------------------------------------------------------------------

class TestPayloadStructure:
    @patch("app.services.webhooks.requests.post")
    def test_payload_contains_required_fields(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook", events=["portfolio_update"])
        mgr.trigger_event("portfolio_update", {"total_value": 10000})

        call_kwargs = mock_post.call_args
        body_str = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs.kwargs["data"]
        body = json.loads(body_str)
        assert body["event_type"] == "portfolio_update"
        assert body["data"]["total_value"] == 10000
        assert "timestamp" in body
        assert "delivery_id" in body

    @patch("app.services.webhooks.requests.post")
    def test_custom_headers_sent(self, mock_post):
        mock_post.return_value = _mock_response(200)
        mgr = WebhookManager()
        mgr.register_webhook("https://example.com/hook", events=["risk_alert"])
        mgr.trigger_event("risk_alert")

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Content-Type"] == "application/json"
        assert headers["X-FinMind-Event"] == "risk_alert"
        assert "X-FinMind-Delivery" in headers
        assert "X-FinMind-Signature" in headers
