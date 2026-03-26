"""
Tests for signed webhook system.
"""

import json
import time
import pytest
from unittest.mock import patch, MagicMock

from app import create_app
from app.extensions import db
from app.models import User, WebhookSubscription, WebhookDelivery, WebhookEvent
from app.services.webhook import (
    _sign_payload,
    _build_headers,
    verify_webhook_signature,
    emit_webhook,
)


@pytest.fixture
def app():
    """Create test app."""
    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(client, app):
    """Get auth token for a test user."""
    with app.app_context():
        user = User(email="test@example.com", password_hash="fakehash")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "password"},
    )
    token = response.get_json().get("access_token")
    return {"Authorization": f"Bearer {token}"}, uid


class TestWebhookSignature:
    """Tests for webhook signature generation and verification."""

    def test_sign_payload_produces_hex_string(self):
        payload = '{"event":"test"}'
        timestamp = "1234567890"
        secret = "mysecret"
        sig = _sign_payload(timestamp, payload, secret)
        assert len(sig) == 64  # SHA256 hex
        assert all(c in "0123456789abcdef" for c in sig)

    def test_sign_payload_is_deterministic(self):
        payload = '{"event":"test"}'
        timestamp = "1234567890"
        secret = "mysecret"
        sig1 = _sign_payload(timestamp, payload, secret)
        sig2 = _sign_payload(timestamp, payload, secret)
        assert sig1 == sig2

    def test_sign_payload_changes_with_secret(self):
        payload = '{"event":"test"}'
        timestamp = "1234567890"
        sig1 = _sign_payload(timestamp, payload, "secret1")
        sig2 = _sign_payload(timestamp, payload, "secret2")
        assert sig1 != sig2

    def test_build_headers_contains_required_fields(self):
        payload = '{"event":"test"}'
        secret = "mysecret"
        event_type = "expense.created"
        headers = _build_headers(payload, secret, event_type)
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Webhook-Event"] == event_type
        assert "X-Webhook-Timestamp" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")

    def test_verify_webhook_signature_valid(self):
        payload = '{"event":"test"}'
        timestamp = str(int(time.time()))
        secret = "mysecret"
        sig = _sign_payload(timestamp, payload, secret)
        assert verify_webhook_signature(
            payload, timestamp, f"sha256={sig}", secret
        )

    def test_verify_webhook_signature_invalid(self):
        payload = '{"event":"test"}'
        timestamp = str(int(time.time()))
        secret = "mysecret"
        assert not verify_webhook_signature(
            payload, timestamp, "sha256=invalid", secret
        )

    def test_verify_webhook_signature_old_timestamp_rejected(self):
        payload = '{"event":"test"}'
        timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        secret = "mysecret"
        sig = _sign_payload(timestamp, payload, secret)
        assert not verify_webhook_signature(
            payload, timestamp, f"sha256={sig}", secret
        )


class TestWebhookSubscriptionAPI:
    """Tests for webhook subscription CRUD endpoints."""

    def test_list_event_types(self, client, auth_headers):
        headers, _uid = auth_headers
        response = client.get("/webhooks/events", headers=headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "events" in data
        assert "expense.created" in data["events"]
        assert "expense.updated" in data["events"]
        assert "expense.deleted" in data["events"]
        assert "bill.due" in data["events"]
        assert "reminder.sent" in data["events"]

    def test_create_subscription(self, client, auth_headers, app):
        headers, uid = auth_headers
        response = client.post(
            "/webhooks",
            headers=headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["expense.created", "expense.updated"],
            },
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["url"] == "https://example.com/webhook"
        assert data["events"] == ["expense.created", "expense.updated"]
        assert "secret" in data  # Secret shown at creation only
        assert "id" in data

    def test_create_subscription_invalid_url(self, client, auth_headers):
        headers, _uid = auth_headers
        response = client.post(
            "/webhooks",
            headers=headers,
            json={
                "url": "not-a-url",
                "events": ["expense.created"],
            },
        )
        assert response.status_code == 400
        assert "url" in response.get_json().get("error", "").lower()

    def test_create_subscription_invalid_event(self, client, auth_headers):
        headers, _uid = auth_headers
        response = client.post(
            "/webhooks",
            headers=headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["invalid.event"],
            },
        )
        assert response.status_code == 400
        assert "invalid" in response.get_json().get("error", "").lower()

    def test_list_subscriptions(self, client, auth_headers, app):
        headers, uid = auth_headers
        # Create a subscription first
        client.post(
            "/webhooks",
            headers=headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["expense.created"],
            },
        )
        response = client.get("/webhooks", headers=headers)
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1

    def test_delete_subscription(self, client, auth_headers, app):
        headers, uid = auth_headers
        # Create
        create_resp = client.post(
            "/webhooks",
            headers=headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["expense.created"],
            },
        )
        sub_id = create_resp.get_json()["id"]
        # Delete
        response = client.delete(f"/webhooks/{sub_id}", headers=headers)
        assert response.status_code == 200
        # Verify deleted
        response = client.get(f"/webhooks/{sub_id}", headers=headers)
        assert response.status_code == 404


class TestWebhookEmission:
    """Tests for webhook emission on events."""

    @patch("app.services.webhook._process_delivery")
    def test_emit_webhook_creates_delivery(self, mock_process, client, auth_headers, app):
        headers, uid = auth_headers
        # Create subscription
        client.post(
            "/webhooks",
            headers=headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["expense.created"],
            },
        )
        # Emit manually
        with app.app_context():
            emit_webhook(
                user_id=uid,
                event_type=WebhookEvent.EXPENSE_CREATED,
                data={"id": 1, "amount": 100.0},
            )
        # Verify delivery was queued (async but mocked)
        mock_process.assert_called()

    @patch("app.services.webhook._process_delivery")
    def test_emit_webhook_no_subscription(self, mock_process, client, auth_headers, app):
        headers, uid = auth_headers
        # Don't create any subscription
        with app.app_context():
            emit_webhook(
                user_id=uid,
                event_type=WebhookEvent.EXPENSE_CREATED,
                data={"id": 1, "amount": 100.0},
            )
        # No delivery should be attempted
        mock_process.assert_not_called()
