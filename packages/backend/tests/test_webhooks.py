import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from app import create_app
from app.extensions import db as _db
from app.config import Settings


@pytest.fixture(scope="session")
def app():
    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="test-secret",
    )
    application = create_app(settings)
    with application.app_context():
        _db.create_all()
        yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(client):
    """Register and login a test user, return JWT headers."""
    client.post("/auth/register", json={"email": "webhook@test.com", "password": "Password1!"})
    resp = client.post("/auth/login", json={"email": "webhook@test.com", "password": "Password1!"})
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestWebhookRegistration:
    def test_register_endpoint(self, client, auth_headers):
        resp = client.post("/webhooks", json={"url": "https://example.com/hook"}, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["url"] == "https://example.com/hook"
        assert "secret" in data
        assert len(data["secret"]) == 64

    def test_register_invalid_url(self, client, auth_headers):
        resp = client.post("/webhooks", json={"url": "not-a-url"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_list_endpoints(self, client, auth_headers):
        client.post("/webhooks", json={"url": "https://example.com/hook2"}, headers=auth_headers)
        resp = client.get("/webhooks", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_delete_endpoint(self, client, auth_headers):
        r = client.post("/webhooks", json={"url": "https://example.com/delete-me"}, headers=auth_headers)
        eid = r.get_json()["id"]
        resp = client.delete(f"/webhooks/{eid}", headers=auth_headers)
        assert resp.status_code == 200


class TestWebhookSigning:
    def test_signature_valid(self):
        from app.services.webhooks import _sign_payload
        secret = "mysecret"
        payload = b'{"event":"expense.created"}'
        sig = _sign_payload(secret, payload)
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_signature_unique_per_payload(self):
        from app.services.webhooks import _sign_payload
        secret = "mysecret"
        sig1 = _sign_payload(secret, b"payload1")
        sig2 = _sign_payload(secret, b"payload2")
        assert sig1 != sig2


class TestWebhookDelivery:
    @patch("app.services.webhooks.requests.post")
    def test_emit_calls_endpoint(self, mock_post, app, auth_headers, client):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        with app.app_context():
            from app.models import WebhookEndpoint
            from app.services.webhooks import emit_webhook
            ep = WebhookEndpoint(user_id=1, url="https://example.com/hook", secret="abc" * 21 + "a")
            _db.session.add(ep)
            _db.session.commit()
            emit_webhook(1, "expense.created", {"amount": 100})
            assert mock_post.called
            call_kwargs = mock_post.call_args
            headers = call_kwargs[1]["headers"]
            assert headers["X-FinMind-Event"] == "expense.created"
            assert headers["X-FinMind-Signature-256"].startswith("sha256=")

    @patch("app.services.webhooks.requests.post")
    def test_retry_on_failure(self, mock_post, app):
        mock_post.return_value = MagicMock(status_code=500, text="error")
        with app.app_context():
            from app.models import WebhookEndpoint
            from app.services.webhooks import _deliver
            ep = WebhookEndpoint(user_id=1, url="https://example.com/retry", secret="x" * 64)
            _db.session.add(ep)
            _db.session.commit()
            with patch("app.services.webhooks.time.sleep"):
                _deliver(ep, "test.event", b'{"event":"test"}')
            assert mock_post.call_count == 3  # MAX_RETRIES
