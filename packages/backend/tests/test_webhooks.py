"""
Tests for webhook functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import User, Expense, Category


@pytest.fixture
def app():
    """Create test application."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        webhook_url="https://example.com/webhook",
        webhook_secret="test-secret",
    )
    app = create_app(settings)
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def auth_headers(client):
    """Create authenticated headers."""
    # Register a test user
    client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "testpassword123",
        },
    )
    # Login
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    token = response.json["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestWebhookConfig:
    """Test webhook configuration endpoints."""

    def test_get_webhook_config(self, client, auth_headers):
        """Test getting webhook configuration."""
        response = client.get("/api/webhooks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json
        assert data["enabled"] is True
        assert data["webhook_url"] == "https://example.com/webhook"
        assert data["has_secret"] is True


class TestWebhookEvents:
    """Test webhook event emission."""

    @patch("app.services.webhooks.requests.post")
    def test_expense_created_emits_webhook(self, mock_post, client, auth_headers):
        """Test that creating an expense emits a webhook."""
        mock_post.return_value = MagicMock(status_code=200, text="OK")

        # Create a category first
        client.post(
            "/categories",
            headers=auth_headers,
            json={"name": "Food"},
        )

        # Create an expense
        response = client.post(
            "/expenses",
            headers=auth_headers,
            json={
                "amount": 50.00,
                "currency": "USD",
                "description": "Lunch",
                "date": "2026-03-03",
                "category_id": 1,
            },
        )
        assert response.status_code == 201

        # Verify webhook was called
        assert mock_post.called
        call_args = mock_post.call_args
        payload = call_args.kwargs["data"]
        import json
        payload_data = json.loads(payload)
        assert payload_data["type"] == "expense.created"
        assert payload_data["data"]["amount"] == 50.00
        assert payload_data["data"]["description"] == "Lunch"

    @patch("app.services.webhooks.requests.post")
    def test_expense_updated_emits_webhook(self, mock_post, client, auth_headers):
        """Test that updating an expense emits a webhook."""
        mock_post.return_value = MagicMock(status_code=200, text="OK")

        # Create a category and expense first
        client.post("/categories", headers=auth_headers, json={"name": "Food"})
        client.post(
            "/expenses",
            headers=auth_headers,
            json={
                "amount": 50.00,
                "currency": "USD",
                "description": "Lunch",
                "date": "2026-03-03",
                "category_id": 1,
            },
        )

        # Update the expense
        response = client.patch(
            "/expenses/1",
            headers=auth_headers,
            json={"amount": 75.00},
        )
        assert response.status_code == 200

        # Verify webhook was called
        assert mock_post.called

    @patch("app.services.webhooks.requests.post")
    def test_expense_deleted_emits_webhook(self, mock_post, client, auth_headers):
        """Test that deleting an expense emits a webhook."""
        mock_post.return_value = MagicMock(status_code=200, text="OK")

        # Create category and expense
        client.post("/categories", headers=auth_headers, json={"name": "Food"})
        client.post(
            "/expenses",
            headers=auth_headers,
            json={
                "amount": 50.00,
                "currency": "USD",
                "description": "Lunch",
                "date": "2026-03-03",
            },
        )

        # Delete the expense
        response = client.delete("/expenses/1", headers=auth_headers)
        assert response.status_code == 200

        # Verify webhook was called
        assert mock_post.called

    @patch("app.services.webhooks.requests.post")
    def test_category_created_emits_webhook(self, mock_post, client, auth_headers):
        """Test that creating a category emits a webhook."""
        mock_post.return_value = MagicMock(status_code=200, text="OK")

        response = client.post(
            "/categories",
            headers=auth_headers,
            json={"name": "Entertainment"},
        )
        assert response.status_code == 201

        # Verify webhook was called
        assert mock_post.called
        import json
        payload = json.loads(mock_post.call_args.kwargs["data"])
        assert payload["type"] == "category.created"

    @patch("app.services.webhooks.requests.post")
    def test_webhook_retry_on_failure(self, mock_post, client, auth_headers):
        """Test that webhooks are retried on failure."""
        # First two calls fail, third succeeds
        mock_post.side_effect = [
            MagicMock(status_code=500, text="Server Error"),
            MagicMock(status_code=500, text="Server Error"),
            MagicMock(status_code=200, text="OK"),
        ]

        response = client.post(
            "/categories",
            headers=auth_headers,
            json={"name": "RetryTest"},
        )
        assert response.status_code == 201

        # Should have attempted 3 times
        assert mock_post.call_count == 3


class TestWebhookSignature:
    """Test webhook signature generation."""

    def test_signature_generation(self):
        """Test that signatures are generated correctly."""
        from app.services.webhooks import WebhookDelivery

        delivery = WebhookDelivery(
            event_type="test.event",
            payload={"data": "test"},
            webhook_url="https://example.com/webhook",
            secret="my-secret",
        )

        payload = '{"data": "test"}'
        signature = delivery._generate_signature(payload)

        import hmac
        import hashlib
        expected = hmac.new(
            "my-secret".encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert signature == f"sha256={expected}"

    def test_no_signature_without_secret(self):
        """Test that no signature is generated without a secret."""
        from app.services.webhooks import WebhookDelivery

        delivery = WebhookDelivery(
            event_type="test.event",
            payload={"data": "test"},
            webhook_url="https://example.com/webhook",
            secret=None,
        )

        payload = '{"data": "test"}'
        signature = delivery._generate_signature(payload)
        assert signature is None
