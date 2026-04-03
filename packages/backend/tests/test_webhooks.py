"""Tests for Webhook Event System (issue #77)."""
import time
from unittest.mock import patch, MagicMock

import pytest
from flask_jwt_extended import create_access_token

from app.webhooks import (
    WebhookSubscription,
    WebhookDelivery,
    WebhookEvent,
    _sign_payload,
    _build_headers,
    emit,
)


REDIS_MOCK = MagicMock()
REDIS_MOCK.setex.return_value = True
REDIS_MOCK.get.return_value = None
REDIS_MOCK.delete.return_value = True
REDIS_MOCK.flushdb.return_value = True


@pytest.fixture()
def auth_header(app_fixture):
    """Generate JWT token directly, bypassing Redis."""
    with app_fixture.app_context():
        # Create a user via DB directly
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        user = User(email="webhooktest@test.com", password_hash=generate_password_hash("Pass1234!"))
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
        return {"Authorization": f"Bearer {token}"}


# Signature tests

class TestSignature:
    def test_sign_payload_returns_hex_string(self):
        sig = _sign_payload("secret", 1700000000, b"hello")
        assert isinstance(sig, str)
        assert len(sig) == 64

    def test_sign_payload_different_secrets_differ(self):
        ts = int(time.time())
        s1 = _sign_payload("secret-a", ts, b"payload")
        s2 = _sign_payload("secret-b", ts, b"payload")
        assert s1 != s2

    def test_sign_payload_different_timestamps_differ(self):
        s1 = _sign_payload("secret", 1000, b"payload")
        s2 = _sign_payload("secret", 2000, b"payload")
        assert s1 != s2

    def test_build_headers_contain_signature(self):
        headers = _build_headers("secret", b"payload", "corr-id-123")
        assert "X-FinMind-Signature" in headers
        assert headers["X-FinMind-Signature"].startswith("t=")
        assert "v1=" in headers["X-FinMind-Signature"]

    def test_build_headers_contain_correlation_id(self):
        headers = _build_headers("secret", b"payload", "corr-id-abc")
        assert headers["X-FinMind-Correlation-Id"] == "corr-id-abc"

    def test_sign_deterministic_same_inputs(self):
        sig1 = _sign_payload("sec", 100, b"data")
        sig2 = _sign_payload("sec", 100, b"data")
        assert sig1 == sig2


class TestSubscriptionCRUD:
    def test_create_subscription(self, client, auth_header):
        resp = client.post("/webhooks/", json={
            "url": "https://example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["url"] == "https://example.com/hook"
        assert "expense.created" in data["events"]
        assert "secret" in data

    def test_list_subscriptions_empty(self, client, auth_header):
        resp = client.get("/webhooks/", headers=auth_header)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_then_list(self, client, auth_header):
        client.post("/webhooks/", json={
            "url": "https://list.example.com/hook",
            "events": ["bill.paid"],
        }, headers=auth_header)
        resp = client.get("/webhooks/", headers=auth_header)
        subs = [s for s in resp.get_json() if s["url"] == "https://list.example.com/hook"]
        assert len(subs) >= 1

    def test_get_subscription_by_id(self, client, auth_header):
        create_resp = client.post("/webhooks/", json={
            "url": "https://getbyid.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        sub_id = create_resp.get_json()["id"]
        resp = client.get(f"/webhooks/{sub_id}", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()["id"] == sub_id

    def test_delete_subscription(self, client, auth_header):
        create_resp = client.post("/webhooks/", json={
            "url": "https://delete.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        sub_id = create_resp.get_json()["id"]
        del_resp = client.delete(f"/webhooks/{sub_id}", headers=auth_header)
        assert del_resp.status_code == 200
        assert client.get(f"/webhooks/{sub_id}", headers=auth_header).status_code == 404

    def test_update_subscription_url(self, client, auth_header):
        create_resp = client.post("/webhooks/", json={
            "url": "https://old.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        sub_id = create_resp.get_json()["id"]
        resp = client.put(
            f"/webhooks/{sub_id}",
            json={"url": "https://new.example.com/hook"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.get_json()["url"] == "https://new.example.com/hook"

    def test_create_with_invalid_event(self, client, auth_header):
        resp = client.post("/webhooks/", json={
            "url": "https://example.com/hook",
            "events": ["not.valid.event"],
        }, headers=auth_header)
        assert resp.status_code == 400

    def test_create_missing_url(self, client, auth_header):
        resp = client.post("/webhooks/", json={
            "events": ["expense.created"],
        }, headers=auth_header)
        assert resp.status_code == 400

    def test_list_event_types(self, client):
        resp = client.get("/webhooks/events")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "events" in data
        assert "expense.created" in data["events"]

    def test_toggle_active_false(self, client, auth_header):
        create_resp = client.post("/webhooks/", json={
            "url": "https://toggle.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        sub_id = create_resp.get_json()["id"]
        resp = client.put(
            f"/webhooks/{sub_id}",
            json={"is_active": False},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.get_json()["is_active"] is False


class TestWebhookDelivery:
    @patch("app.webhooks.requests.post")
    def test_emit_calls_subscriber_url(self, mock_post, app_fixture, auth_header, client):
        mock_post.return_value = MagicMock(status_code=200)
        client.post("/webhooks/", json={
            "url": "https://emittest.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        with app_fixture.app_context():
            sub = WebhookSubscription.query.filter_by(url="https://emittest.example.com/hook").first()
            if sub:
                emit(sub.user_id, "expense.created", {"amount": 100})
                assert mock_post.called

    @patch("app.webhooks.requests.post")
    def test_emit_skips_wrong_event(self, mock_post, app_fixture, auth_header, client):
        mock_post.return_value = MagicMock(status_code=200)
        client.post("/webhooks/", json={
            "url": "https://wrongevent.example.com/hook",
            "events": ["bill.paid"],
        }, headers=auth_header)
        with app_fixture.app_context():
            sub = WebhookSubscription.query.filter_by(url="https://wrongevent.example.com/hook").first()
            if sub:
                mock_post.reset_mock()
                emit(sub.user_id, "expense.created", {"amount": 100})
                assert not mock_post.called

    @patch("app.webhooks.requests.post")
    def test_failed_delivery_increments_failures(self, mock_post, app_fixture, auth_header, client):
        mock_post.return_value = MagicMock(status_code=500)
        client.post("/webhooks/", json={
            "url": "https://failtest.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        with app_fixture.app_context():
            from app.extensions import db
            sub = WebhookSubscription.query.filter_by(url="https://failtest.example.com/hook").first()
            if sub:
                emit(sub.user_id, "expense.created", {"amount": 100})
                db.session.refresh(sub)
                assert sub.consecutive_failures >= 1

    @patch("app.webhooks.requests.post")
    def test_delivery_record_created(self, mock_post, app_fixture, auth_header, client):
        mock_post.return_value = MagicMock(status_code=200)
        client.post("/webhooks/", json={
            "url": "https://recordtest.example.com/hook",
            "events": ["expense.created"],
        }, headers=auth_header)
        with app_fixture.app_context():
            sub = WebhookSubscription.query.filter_by(url="https://recordtest.example.com/hook").first()
            if sub:
                emit(sub.user_id, "expense.created", {"amount": 200})
                delivery = WebhookDelivery.query.filter_by(subscription_id=sub.id).first()
                assert delivery is not None
                assert delivery.succeeded
                assert delivery.correlation_id != ""
