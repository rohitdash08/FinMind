"""Tests for webhook functionality."""
import json
import hmac
import hashlib
from datetime import datetime, timedelta
import pytest
from app.models_webhook import (
    WebhookSubscription,
    WebhookDelivery,
    WebhookEventType,
    WebhookStatus,
    WebhookDeliveryStatus,
)
from app.services.webhook_service import (
    generate_signature,
    verify_signature,
    create_delivery,
    deliver_webhook,
    schedule_retry,
    trigger_event,
)


class TestWebhookSignature:
    """Test signature generation and verification."""

    def test_generate_signature(self):
        payload = '{"test": "data"}'
        secret = "my-secret-key"
        signature = generate_signature(payload, secret)

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex length

    def test_verify_signature_valid(self):
        payload = '{"test": "data"}'
        secret = "my-secret-key"
        signature = generate_signature(payload, secret)

        assert verify_signature(payload, signature, secret) is True

    def test_verify_signature_invalid(self):
        payload = '{"test": "data"}'
        secret = "my-secret-key"

        assert verify_signature(payload, "wrong-signature", secret) is False

    def test_verify_signature_tampered_payload(self):
        payload = '{"test": "data"}'
        secret = "my-secret-key"
        signature = generate_signature(payload, secret)

        tampered_payload = '{"test": "tampered"}'
        assert verify_signature(tampered_payload, signature, secret) is False


class TestWebhookDelivery:
    """Test webhook delivery functionality."""

    def test_create_delivery(self, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        payload = {"amount": 100, "currency": "INR"}
        delivery = create_delivery(
            subscription_id=subscription.id,
            event_type=WebhookEventType.EXPENSE_CREATED.value,
            payload=payload,
        )

        assert delivery.id is not None
        assert delivery.subscription_id == subscription.id
        assert delivery.event_type == WebhookEventType.EXPENSE_CREATED.value
        assert delivery.payload == payload
        assert delivery.status == WebhookDeliveryStatus.PENDING

    def test_schedule_retry(self, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        delivery = create_delivery(
            subscription_id=subscription.id,
            event_type=WebhookEventType.EXPENSE_CREATED.value,
            payload={},
        )
        delivery.status = WebhookDeliveryStatus.FAILED
        db_session.commit()

        result = schedule_retry(delivery)

        assert result is True
        assert delivery.retry_count == 1
        assert delivery.status == WebhookDeliveryStatus.RETRYING
        assert delivery.scheduled_at > datetime.utcnow()

    def test_schedule_retry_max_retries(self, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        delivery = create_delivery(
            subscription_id=subscription.id,
            event_type=WebhookEventType.EXPENSE_CREATED.value,
            payload={},
        )
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.retry_count = 5  # MAX_RETRIES
        db_session.commit()

        result = schedule_retry(delivery)

        assert result is False


class TestWebhookAPI:
    """Test webhook API endpoints."""

    def test_list_webhooks_empty(self, client, auth_headers):
        response = client.get("/api/webhooks", headers=auth_headers)

        assert response.status_code == 200
        assert response.json == []

    def test_create_webhook(self, client, auth_headers):
        data = {
            "url": "https://example.com/webhook",
            "events": ["expense.created", "bill.due"],
            "description": "Test webhook",
        }

        response = client.post(
            "/api/webhooks",
            headers=auth_headers,
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == 201
        assert response.json["url"] == data["url"]
        assert response.json["events"] == data["events"]
        assert response.json["secret"] is not None  # Secret returned on creation
        assert response.json["status"] == "active"

    def test_create_webhook_missing_url(self, client, auth_headers):
        data = {"events": ["expense.created"]}

        response = client.post(
            "/api/webhooks",
            headers=auth_headers,
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "error" in response.json

    def test_create_webhook_invalid_event(self, client, auth_headers):
        data = {
            "url": "https://example.com/webhook",
            "events": ["invalid.event"],
        }

        response = client.post(
            "/api/webhooks",
            headers=auth_headers,
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "Invalid event types" in response.json["error"]

    def test_get_webhook(self, client, auth_headers, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        response = client.get(f"/api/webhooks/{subscription.id}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json["url"] == subscription.url
        assert "secret" not in response.json  # Secret not returned on get

    def test_update_webhook(self, client, auth_headers, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        update_data = {
            "url": "https://new-url.com/webhook",
            "description": "Updated description",
        }

        response = client.put(
            f"/api/webhooks/{subscription.id}",
            headers=auth_headers,
            data=json.dumps(update_data),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json["url"] == update_data["url"]
        assert response.json["description"] == update_data["description"]

    def test_delete_webhook(self, client, auth_headers, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        response = client.delete(
            f"/api/webhooks/{subscription.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "deleted successfully" in response.json["message"]

        # Verify deletion
        get_response = client.get(f"/api/webhooks/{subscription.id}", headers=auth_headers)
        assert get_response.status_code == 404

    def test_regenerate_secret(self, client, auth_headers, db_session, user):
        subscription = WebhookSubscription(
            user_id=user.id,
            url="https://example.com/webhook",
            secret="old-secret",
            events=[WebhookEventType.EXPENSE_CREATED.value],
        )
        db_session.add(subscription)
        db_session.commit()

        old_secret = subscription.secret

        response = client.post(
            f"/api/webhooks/{subscription.id}/regenerate-secret",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json["secret"] != old_secret
        assert "Secret regenerated" in response.json["message"]

    def test_list_event_types(self, client):
        response = client.get("/api/webhooks/events")

        assert response.status_code == 200
        events = response.json
        assert len(events) > 0
        assert all("type" in e and "description" in e for e in events)
