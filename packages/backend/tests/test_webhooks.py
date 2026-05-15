import hashlib
import hmac
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import WebhookDelivery


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture()
def auth_header(client, monkeypatch):
    monkeypatch.setattr("app.routes.auth.redis_client.setex", lambda *args: True)
    monkeypatch.setattr(
        "app.services.cache.redis_client.scan", lambda **kwargs: (0, [])
    )
    monkeypatch.setattr("app.services.cache.redis_client.delete", lambda *args: 0)
    email = "webhooks@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_webhook_endpoint_receives_signed_expense_event(
    client, auth_header, monkeypatch
):
    captured = {}

    def _fake_post(url, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse(204)

    monkeypatch.setattr("app.services.webhooks.requests.post", _fake_post)

    r = client.post(
        "/webhooks",
        json={
            "url": "https://example.com/hooks/finmind",
            "secret": "super-secret",
            "event_types": ["expense.created"],
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    endpoint_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Webhook lunch", "date": "2026-05-15"},
        headers=auth_header,
    )
    assert r.status_code == 201

    assert captured["url"] == "https://example.com/hooks/finmind"
    assert captured["headers"]["X-FinMind-Event"] == "expense.created"
    expected_sig = hmac.new(
        b"super-secret", captured["data"].encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert captured["headers"]["X-FinMind-Signature"] == f"sha256={expected_sig}"

    r = client.get("/webhooks/deliveries", headers=auth_header)
    assert r.status_code == 200
    delivery = r.get_json()[0]
    assert delivery["endpoint_id"] == endpoint_id
    assert delivery["event_type"] == "expense.created"
    assert delivery["status"] == "delivered"
    assert delivery["attempts"] == 1


def test_webhook_retry_redelivers_pending_delivery(
    app_fixture, client, auth_header, monkeypatch
):
    responses = [_FakeResponse(500), _FakeResponse(200)]

    def _fake_post(url, data, headers, timeout):
        return responses.pop(0)

    monkeypatch.setattr("app.services.webhooks.requests.post", _fake_post)

    r = client.post(
        "/webhooks",
        json={
            "url": "https://example.com/hooks/retry",
            "secret": "retry-secret",
            "event_types": ["expense.created"],
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={"amount": 8, "description": "Retry test", "date": "2026-05-15"},
        headers=auth_header,
    )
    assert r.status_code == 201

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == "pending"
        assert delivery.attempts == 1
        assert delivery.last_error == "HTTP 500"
        delivery.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    r = client.post("/webhooks/deliveries/retry", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["retried"] == 1

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == "delivered"
        assert delivery.attempts == 2
        assert delivery.last_error is None
