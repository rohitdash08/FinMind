"""Tests for the Webhook Event System.

Covers:
  - Webhook CRUD (create, list, get, update, delete)
  - HMAC-SHA256 signature generation & verification
  - Event emission & delivery
  - Retry & dead-letter handling
  - Delivery log listing
  - Auto-disable after consecutive failures
  - Event type validation
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import (
    DeliveryStatus,
    Webhook,
    WebhookDelivery,
    WebhookEventType,
)
from app.services.webhooks import (
    MAX_CONSECUTIVE_FAILURES,
    RETRY_DELAYS,
    _attempt_delivery,
    _create_delivery,
    _handle_failure,
    emit_event,
    retry_pending_deliveries,
    sign_payload,
    verify_signature,
)


# ─── Signature Tests ─────────────────────────────────────────────────────────


class TestSignature:
    def test_sign_and_verify(self):
        secret = "my-secret"
        payload = b'{"event": "expense.created"}'
        sig = sign_payload(secret, payload)
        assert verify_signature(secret, payload, sig) is True

    def test_verify_bad_signature(self):
        secret = "my-secret"
        payload = b'{"event": "expense.created"}'
        assert verify_signature(secret, payload, "bad-sig") is False

    def test_verify_wrong_secret(self):
        payload = b'{"event": "expense.created"}'
        sig = sign_payload("correct-secret", payload)
        assert verify_signature("wrong-secret", payload, sig) is False

    def test_signature_deterministic(self):
        secret = "test"
        payload = b"hello"
        assert sign_payload(secret, payload) == sign_payload(secret, payload)

    def test_different_payloads_different_sigs(self):
        secret = "test"
        sig1 = sign_payload(secret, b"payload1")
        sig2 = sign_payload(secret, b"payload2")
        assert sig1 != sig2


# ─── Webhook CRUD Tests ─────────────────────────────────────────────────────


class TestWebhookCRUD:
    def test_create_webhook(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["expense.created"]},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["url"] == "https://example.com/hook"
        assert data["events"] == ["expense.created"]
        assert data["active"] is True
        assert "secret" in data  # Secret returned on creation
        assert len(data["secret"]) == 64  # 32 bytes hex

    def test_create_webhook_with_custom_secret(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={
                "url": "https://example.com/hook",
                "secret": "my-custom-secret",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["secret"] == "my-custom-secret"

    def test_create_webhook_wildcard(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook"},
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["events"] == ["*"]

    def test_create_webhook_invalid_url(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "not-a-url"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_webhook_invalid_event(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["invalid.event"]},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_list_webhooks(self, client, auth_header):
        # Create two webhooks
        client.post(
            "/webhooks",
            json={"url": "https://a.com/hook"},
            headers=auth_header,
        )
        client.post(
            "/webhooks",
            json={"url": "https://b.com/hook"},
            headers=auth_header,
        )
        r = client.get("/webhooks", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 2

    def test_get_webhook(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook"},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]
        r = client.get(f"/webhooks/{wh_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == wh_id

    def test_get_webhook_not_found(self, client, auth_header):
        r = client.get("/webhooks/99999", headers=auth_header)
        assert r.status_code == 404

    def test_update_webhook(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://old.com/hook"},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]
        r = client.patch(
            f"/webhooks/{wh_id}",
            json={"url": "https://new.com/hook", "active": False},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["url"] == "https://new.com/hook"
        assert data["active"] is False

    def test_update_webhook_reactivate_resets_failures(self, client, auth_header, app_fixture):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook"},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]
        # Manually set failure count
        with app_fixture.app_context():
            from app.extensions import db as test_db
            wh = test_db.session.get(Webhook, wh_id)
            wh.failure_count = 5
            test_db.session.commit()
        # Reactivate
        r = client.patch(
            f"/webhooks/{wh_id}",
            json={"active": True},
            headers=auth_header,
        )
        assert r.get_json()["failure_count"] == 0

    def test_delete_webhook(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook"},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]
        r = client.delete(f"/webhooks/{wh_id}", headers=auth_header)
        assert r.status_code == 200
        r = client.get(f"/webhooks/{wh_id}", headers=auth_header)
        assert r.status_code == 404


# ─── Event Emission Tests ───────────────────────────────────────────────────


class TestEventEmission:
    @patch("app.services.webhooks.http_requests.post")
    def test_emit_event_success(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_post.return_value = mock_resp

        # Create a webhook
        r = client.post(
            "/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["expense.created"],
                "secret": "test-secret",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        with app_fixture.app_context():
            delivery_ids = emit_event(
                user_id=1,
                event_type="expense.created",
                data={"id": 1, "amount": 42.50},
            )
            assert len(delivery_ids) == 1

            # Verify the delivery was successful
            from app.extensions import db as test_db
            delivery = test_db.session.get(WebhookDelivery, delivery_ids[0])
            assert delivery.status == DeliveryStatus.SUCCESS.value
            assert delivery.attempts == 1
            assert delivery.last_status_code == 200

        # Verify HMAC signature was sent
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "X-FinMind-Signature" in headers
        assert headers["X-FinMind-Signature"].startswith("sha256=")

    @patch("app.services.webhooks.http_requests.post")
    def test_emit_event_no_matching_webhooks(self, mock_post, client, auth_header, app_fixture):
        # Webhook subscribes to expense.created but we emit bill.created
        client.post(
            "/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["expense.created"],
            },
            headers=auth_header,
        )

        with app_fixture.app_context():
            delivery_ids = emit_event(
                user_id=1,
                event_type="bill.created",
                data={"id": 1},
            )
            assert len(delivery_ids) == 0

        mock_post.assert_not_called()

    @patch("app.services.webhooks.http_requests.post")
    def test_emit_event_wildcard_matches_all(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["*"]},
            headers=auth_header,
        )

        with app_fixture.app_context():
            delivery_ids = emit_event(
                user_id=1,
                event_type="bill.created",
                data={"id": 1},
            )
            assert len(delivery_ids) == 1


# ─── Retry & Dead Letter Tests ──────────────────────────────────────────────


class TestRetryAndDeadLetter:
    @patch("app.services.webhooks.http_requests.post")
    def test_failed_delivery_schedules_retry(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["*"]},
            headers=auth_header,
        )

        with app_fixture.app_context():
            delivery_ids = emit_event(
                user_id=1,
                event_type="expense.created",
                data={"id": 1},
            )
            from app.extensions import db as test_db
            delivery = test_db.session.get(WebhookDelivery, delivery_ids[0])
            assert delivery.status == DeliveryStatus.PENDING.value
            assert delivery.attempts == 1
            assert delivery.next_retry_at is not None
            assert delivery.last_status_code == 500

    @patch("app.services.webhooks.http_requests.post")
    def test_delivery_becomes_dead_after_max_retries(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"
        mock_post.return_value = mock_resp

        client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["*"]},
            headers=auth_header,
        )

        with app_fixture.app_context():
            from app.extensions import db as test_db
            delivery_ids = emit_event(
                user_id=1,
                event_type="expense.created",
                data={"id": 1},
            )
            delivery = test_db.session.get(WebhookDelivery, delivery_ids[0])
            # Simulate max retries reached
            delivery.attempts = 4  # Next attempt will be the 5th
            delivery.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
            test_db.session.commit()

            wh = test_db.session.get(Webhook, delivery.webhook_id)
            _attempt_delivery(wh, delivery)

            test_db.session.refresh(delivery)
            assert delivery.status == DeliveryStatus.DEAD.value
            assert delivery.completed_at is not None

    @patch("app.services.webhooks.http_requests.post")
    def test_auto_disable_after_consecutive_failures(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"
        mock_post.return_value = mock_resp

        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["*"]},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]

        with app_fixture.app_context():
            from app.extensions import db as test_db
            wh = test_db.session.get(Webhook, wh_id)
            wh.failure_count = MAX_CONSECUTIVE_FAILURES - 1
            test_db.session.commit()

            delivery_ids = emit_event(
                user_id=1,
                event_type="expense.created",
                data={"id": 1},
            )

            test_db.session.refresh(wh)
            assert wh.active is False
            assert wh.failure_count >= MAX_CONSECUTIVE_FAILURES

    @patch("app.services.webhooks.http_requests.post")
    def test_retry_pending_deliveries(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["*"]},
            headers=auth_header,
        )

        with app_fixture.app_context():
            from app.extensions import db as test_db
            # Create a delivery that's due for retry
            wh = test_db.session.query(Webhook).first()
            delivery = _create_delivery(wh, "expense.created", {"id": 1})
            delivery.attempts = 1
            delivery.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
            test_db.session.commit()

            count = retry_pending_deliveries()
            assert count == 1

            test_db.session.refresh(delivery)
            assert delivery.status == DeliveryStatus.SUCCESS.value


# ─── Delivery Log Tests ─────────────────────────────────────────────────────


class TestDeliveryLog:
    @patch("app.services.webhooks.http_requests.post")
    def test_list_deliveries(self, mock_post, client, auth_header, app_fixture):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["*"]},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]

        with app_fixture.app_context():
            emit_event(1, "expense.created", {"id": 1})
            emit_event(1, "expense.updated", {"id": 1})

        r = client.get(f"/webhooks/{wh_id}/deliveries", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 2
        # Check fields
        assert "delivery_id" in data[0]
        assert "event_type" in data[0]
        assert "status" in data[0]
        assert "attempts" in data[0]


# ─── Test Ping Endpoint ─────────────────────────────────────────────────────


class TestPing:
    @patch("app.services.webhooks.http_requests.post")
    def test_test_webhook(self, mock_post, client, auth_header):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook"},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]

        r = client.post(f"/webhooks/{wh_id}/test", headers=auth_header)
        assert r.status_code == 200
        assert "delivery_ids" in r.get_json()

    def test_test_disabled_webhook(self, client, auth_header):
        r = client.post(
            "/webhooks",
            json={"url": "https://example.com/hook"},
            headers=auth_header,
        )
        wh_id = r.get_json()["id"]
        # Disable it
        client.patch(
            f"/webhooks/{wh_id}",
            json={"active": False},
            headers=auth_header,
        )
        r = client.post(f"/webhooks/{wh_id}/test", headers=auth_header)
        assert r.status_code == 400


# ─── Integration: Expense Events ────────────────────────────────────────────


class TestExpenseWebhookIntegration:
    @patch("app.services.webhooks.http_requests.post")
    def test_expense_create_triggers_webhook(self, mock_post, client, auth_header):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # Register webhook
        client.post(
            "/webhooks",
            json={"url": "https://example.com/hook", "events": ["expense.created"]},
            headers=auth_header,
        )

        # Create expense
        r = client.post(
            "/expenses",
            json={"amount": 25.50, "description": "Lunch", "date": "2026-02-15"},
            headers=auth_header,
        )
        assert r.status_code == 201

        # Verify webhook was called
        assert mock_post.called
        call_kwargs = mock_post.call_args
        sent_data = call_kwargs.kwargs.get("data") or call_kwargs[1].get("data", b"")
        payload = json.loads(sent_data)
        assert payload["event_type"] == "expense.created"
        assert payload["data"]["amount"] == 25.50
