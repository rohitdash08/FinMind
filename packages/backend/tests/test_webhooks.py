from datetime import datetime, timedelta

import requests
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User, WebhookDelivery, WebhookTarget
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


def _direct_auth_header(client) -> dict[str, str]:
    with client.application.app_context():
        user = User(
            email="direct-webhook@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


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


def test_webhook_delivery_summary_reports_retry_backlog(client):
    auth_header = _direct_auth_header(client)
    target_id = _create_target(client, auth_header, ["expense.created"])

    with client.application.app_context():
        target = db.session.get(WebhookTarget, target_id)
        assert target is not None
        now = datetime.utcnow()
        db.session.add_all(
            [
                WebhookDelivery(
                    target_id=target.id,
                    event_type="expense.created",
                    payload={"type": "expense.created", "data": {"id": 1}},
                    status="pending",
                    attempt_count=2,
                    next_attempt_at=now - timedelta(minutes=5),
                ),
                WebhookDelivery(
                    target_id=target.id,
                    event_type="expense.created",
                    payload={"type": "expense.created", "data": {"id": 2}},
                    status="pending",
                    attempt_count=1,
                    next_attempt_at=now + timedelta(minutes=10),
                ),
                WebhookDelivery(
                    target_id=target.id,
                    event_type="expense.created",
                    payload={"type": "expense.created", "data": {"id": 3}},
                    status="success",
                    attempt_count=1,
                    next_attempt_at=None,
                ),
                WebhookDelivery(
                    target_id=target.id,
                    event_type="expense.created",
                    payload={"type": "expense.created", "data": {"id": 4}},
                    status="failed",
                    attempt_count=8,
                    next_attempt_at=None,
                    response_body="connection failed",
                ),
            ]
        )
        db.session.commit()

    response = client.get("/webhooks/deliveries/summary", headers=auth_header)
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["max_retries"] == WebhookService.MAX_RETRIES
    assert payload["targets_total"] == 1
    assert payload["deliveries"]["pending"] == 2
    assert payload["deliveries"]["success"] == 1
    assert payload["deliveries"]["failed"] == 1
    assert payload["retry_backlog"]["due_now"] == 1
    assert payload["retry_backlog"]["scheduled"] == 1
    assert payload["latest_failure"] is not None
    assert payload["oldest_pending"] is not None
