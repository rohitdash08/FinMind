"""Tests for webhook event system."""
import json
import hashlib
import hmac
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User
from app.services.webhooks import (
    WebhookEventType,
    WebhookEndpoint,
    WebhookDelivery,
    register_endpoint,
    emit_event,
    process_retries,
    MAX_RETRIES,
)


@pytest.fixture
def app():
    """Create test app."""
    from app import create_app
    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    """Create a test user and return JWT headers."""
    with app.app_context():
        user = User(email="test@finmind.io", password_hash="x")
        _db.session.add(user)
        _db.session.commit()
        uid = user.id
    from flask_jwt_extended import create_access_token
    token = create_access_token(identity=str(uid))
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

class TestSignature:
    """Test HMAC signature generation."""

    def test_sign_payload(self, app):
        with app.app_context():
            user = User(email="sig@test.io", password_hash="x")
            _db.session.add(user)
            _db.session.commit()
            ep = register_endpoint(user.id, "https://example.com/hook")
            payload = b'{"test": true}'
            ts = 1700000000
            sig = ep.sign_payload(payload, ts)
            # Verify manually
            msg = f"{ts}.{payload.decode()}".encode()
            expected = hmac.new(ep.secret.encode(), msg, hashlib.sha256).hexdigest()
            assert sig == expected


class TestEmitEvent:
    """Test event emission."""

    @patch("app.services.webhooks.requests.post")
    def test_emit_delivers_to_endpoints(self, mock_post, app):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        with app.app_context():
            user = User(email="emit@test.io", password_hash="x")
            _db.session.add(user)
            _db.session.commit()
            register_endpoint(user.id, "https://example.com/hook1")
            register_endpoint(user.id, "https://example.com/hook2")

            emit_event(WebhookEventType.EXPENSE_CREATED, {"amount": 50.0}, user_id=user.id)
            assert mock_post.call_count == 2

    @patch("app.services.webhooks.requests.post")
    def test_emit_retries_on_failure(self, mock_post, app):
        mock_post.side_effect = Exception("Connection refused")
        with app.app_context():
            user = User(email="retry@test.io", password_hash="x")
            _db.session.add(user)
            _db.session.commit()
            register_endpoint(user.id, "https://example.com/hook")

            emit_event(WebhookEventType.BILL_PAID, {"bill_id": 1}, user_id=user.id)
            delivery = WebhookDelivery.query.first()
            assert delivery is not None
            assert delivery.success is False
            assert delivery.attempts == 1
            assert delivery.next_retry_at is not None


class TestProcessRetries:
    """Test retry processing."""

    @patch("app.services.webhooks.requests.post")
    def test_retry_succeeds(self, mock_post, app):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        with app.app_context():
            user = User(email="retry2@test.io", password_hash="x")
            _db.session.add(user)
            _db.session.commit()
            ep = register_endpoint(user.id, "https://example.com/hook")

            # Create failed delivery
            d = WebhookDelivery(
                endpoint_id=ep.id,
                event_type="test",
                payload='{"test":true}',
                success=False,
                attempts=1,
            )
            _db.session.add(d)
            _db.session.commit()
            d.next_retry_at = None  # Make it eligible for retry

            count = process_retries()
            assert count == 1
            d = WebhookDelivery.query.first()
            assert d.success is True


# ---------------------------------------------------------------------------
# API Tests
# ---------------------------------------------------------------------------

class TestWebhookAPI:
    """Test webhook management API."""

    def test_create_endpoint(self, app, client, auth_headers):
        resp = client.post(
            "/webhooks/endpoints",
            json={"url": "https://example.com/hook", "description": "Test"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["url"] == "https://example.com/hook"
        assert data["secret"].startswith("whsec_")

    def test_create_endpoint_no_url(self, app, client, auth_headers):
        resp = client.post("/webhooks/endpoints", json={}, headers=auth_headers)
        assert resp.status_code == 400

    def test_list_endpoints(self, app, client, auth_headers):
        client.post("/webhooks/endpoints", json={"url": "https://example.com/a"}, headers=auth_headers)
        client.post("/webhooks/endpoints", json={"url": "https://example.com/b"}, headers=auth_headers)
        resp = client.get("/webhooks/endpoints", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_delete_endpoint(self, app, client, auth_headers):
        resp = client.post("/webhooks/endpoints", json={"url": "https://example.com/x"}, headers=auth_headers)
        ep_id = resp.get_json()["id"]
        resp = client.delete(f"/webhooks/endpoints/{ep_id}", headers=auth_headers)
        assert resp.status_code == 204

    def test_delete_other_users_endpoint(self, app, client, auth_headers):
        resp = client.delete("/webhooks/endpoints/9999", headers=auth_headers)
        assert resp.status_code == 404

    def test_list_event_types(self, app, client, auth_headers):
        resp = client.get("/webhooks/event-types", headers=auth_headers)
        assert resp.status_code == 200
        events = resp.get_json()["event_types"]
        assert "expense.created" in events
        assert "bill.paid" in events

    @patch("app.services.webhooks.requests.post")
    def test_test_endpoint(self, mock_post, app, client, auth_headers):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        resp = client.post("/webhooks/endpoints", json={"url": "https://example.com/t"}, headers=auth_headers)
        ep_id = resp.get_json()["id"]
        resp = client.post(f"/webhooks/endpoints/{ep_id}/test", headers=auth_headers)
        assert resp.status_code == 200
