import hashlib
import hmac

import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from app.models import User, WebhookDelivery
from app.extensions import db


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture(autouse=True)
def disable_cache_invalidation(monkeypatch):
    monkeypatch.setattr("app.routes.expenses.cache_delete_patterns", lambda _patterns: None)


@pytest.fixture()
def auth_header(app_fixture):
    with app_fixture.app_context():
        user = User(
            email="webhook-test@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def test_webhook_endpoint_crud_and_event_types(client, auth_header):
    r = client.get("/webhooks/event-types")
    assert r.status_code == 200
    assert "expense.created" in r.get_json()

    r = client.post("/webhooks", json={"url": "not-a-url"}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/webhooks", json={"url": "https://example.com/webhook"}, headers=auth_header
    )
    assert r.status_code == 201
    created = r.get_json()
    endpoint_id = created["id"]
    assert created["url"] == "https://example.com/webhook"
    assert created["active"] is True
    assert created["secret"]

    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    listed = r.get_json()
    assert listed[0]["id"] == endpoint_id
    assert "secret" not in listed[0]

    r = client.patch(
        f"/webhooks/{endpoint_id}",
        json={"url": "https://example.com/updated", "active": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["active"] is False

    r = client.delete(f"/webhooks/{endpoint_id}", headers=auth_header)
    assert r.status_code == 204


def test_expense_create_delivers_signed_webhook_and_records_success(
    client, auth_header, monkeypatch, app_fixture
):
    r = client.post(
        "/webhooks", json={"url": "https://example.com/webhook"}, headers=auth_header
    )
    assert r.status_code == 201
    endpoint = r.get_json()
    secret = endpoint["secret"]
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return _Response(204)

    monkeypatch.setattr("app.services.webhooks.requests.post", fake_post)

    r = client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Coffee", "date": "2026-02-12"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://example.com/webhook"
    assert call["headers"]["X-FinMind-Event"] == "expense.created"
    assert call["headers"]["X-FinMind-Delivery"]
    timestamp = call["headers"]["X-FinMind-Timestamp"]
    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + call["data"],
        hashlib.sha256,
    ).hexdigest()
    assert call["headers"]["X-FinMind-Signature"] == f"sha256={expected}"

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.event_type == "expense.created"
        assert delivery.success is True
        assert delivery.status_code == 204
        assert delivery.attempts == 1

    r = client.get(f"/webhooks/{endpoint['id']}/deliveries", headers=auth_header)
    assert r.status_code == 200
    deliveries = r.get_json()
    assert deliveries[0]["event_type"] == "expense.created"
    assert deliveries[0]["success"] is True


def test_webhook_delivery_retries_and_records_failure(
    client, auth_header, monkeypatch, app_fixture
):
    r = client.post(
        "/webhooks", json={"url": "https://example.com/webhook"}, headers=auth_header
    )
    assert r.status_code == 201
    attempts = []

    def fake_post(url, data, headers, timeout):
        attempts.append(url)
        return _Response(500)

    monkeypatch.setattr("app.services.webhooks.requests.post", fake_post)
    monkeypatch.setattr("app.services.webhooks.time.sleep", lambda _seconds: None)

    r = client.post(
        "/expenses",
        json={"amount": 8.0, "description": "Lunch", "date": "2026-02-13"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert len(attempts) == 3

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.event_type == "expense.created"
        assert delivery.success is False
        assert delivery.status_code == 500
        assert delivery.attempts == 3
        assert delivery.error == "HTTP 500"
