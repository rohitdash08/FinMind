from datetime import datetime, timedelta

import requests

from app.extensions import db
from app.models import WebhookDelivery
from app.services.webhooks import WebhookService


EXPECTED_EVENT_TYPES = {
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.updated",
    "bill.deleted",
    "bill.due",
    "subscription.updated",
    "profile.updated",
}


def _create_target(client, auth_header, events: list[str]):
    response = client.post(
        "/webhooks/targets",
        json={
            "url": "https://example.test/webhook",
            "secret": "super-secret-key",
            "events": events,
        },
        headers=auth_header,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def test_webhook_event_types_documented(client, auth_header):
    response = client.get("/webhooks/event-types", headers=auth_header)
    assert response.status_code == 200

    event_types = {item["type"] for item in response.get_json()}
    assert EXPECTED_EVENT_TYPES.issubset(event_types)


def test_signed_webhook_delivery_for_expense_created(client, auth_header, monkeypatch):
    _create_target(client, auth_header, ["expense.created"])

    captured: dict = {}

    class _Response:
        status_code = 204
        text = "ok"

    def _fake_post(url, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("app.services.webhooks.requests.post", _fake_post)

    response = client.post(
        "/expenses",
        json={
            "amount": 10.5,
            "description": "Coffee",
            "date": "2026-03-01",
        },
        headers=auth_header,
    )
    assert response.status_code == 201

    assert captured["url"] == "https://example.test/webhook"
    assert captured["timeout"] == 10
    assert captured["headers"]["X-FinMind-Event"] == "expense.created"
    assert captured["headers"]["X-FinMind-Signature"].startswith("sha256=")

    timestamp = captured["headers"]["X-FinMind-Timestamp"]
    expected_signature = WebhookService.generate_signature(
        "super-secret-key",
        captured["data"],
        timestamp,
    )
    assert captured["headers"]["X-FinMind-Signature"] == f"sha256={expected_signature}"

    with client.application.app_context():
        deliveries = WebhookDelivery.query.all()
        assert len(deliveries) == 1
        assert deliveries[0].status == "success"
        assert deliveries[0].attempt_count == 1


def test_webhook_retry_and_failure_handling(client, auth_header, monkeypatch):
    _create_target(client, auth_header, ["expense.created"])

    def _always_fail(*_args, **_kwargs):
        raise requests.RequestException("connection failed")

    monkeypatch.setattr("app.services.webhooks.requests.post", _always_fail)

    response = client.post(
        "/expenses",
        json={
            "amount": 20,
            "description": "Lunch",
            "date": "2026-03-02",
        },
        headers=auth_header,
    )
    assert response.status_code == 201

    with client.application.app_context():
        delivery = WebhookDelivery.query.one()
        assert delivery.status == "pending"
        assert delivery.attempt_count == 1
        assert delivery.next_attempt_at is not None
        assert "connection failed" in (delivery.response_body or "")

        delivery.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        delivery.attempt_count = WebhookService.MAX_RETRIES
        db.session.commit()

        delivery_id = delivery.id

    with client.application.app_context():
        WebhookService.process_pending_deliveries()

    with client.application.app_context():
        failed_delivery = db.session.get(WebhookDelivery, delivery_id)
        assert failed_delivery is not None
        assert failed_delivery.status == "failed"
        assert failed_delivery.attempt_count == WebhookService.MAX_RETRIES + 1
