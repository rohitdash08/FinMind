from datetime import datetime

from app.extensions import db
from app.models import WebhookDelivery
from app.services.webhooks import process_due_deliveries, sign_payload


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


def _create_webhook(client, auth_header, *, event_types=None, secret="supersecret"):
    payload = {
        "url": "https://example.com/finmind-webhook",
        "secret": secret,
    }
    if event_types is not None:
        payload["event_types"] = event_types
    r = client.post("/webhooks", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _create_expense(client, auth_header, description="Webhook groceries"):
    payload = {
        "amount": 18.75,
        "currency": "USD",
        "description": description,
        "date": "2026-02-12",
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_webhook_endpoint_queues_signed_delivery_for_expense(
    client, auth_header, monkeypatch
):
    endpoint = _create_webhook(
        client,
        auth_header,
        event_types=["expense.created"],
        secret="supersecret",
    )
    assert endpoint["event_types"] == ["expense.created"]

    _create_expense(client, auth_header)

    r = client.get("/webhooks/deliveries", headers=auth_header)
    assert r.status_code == 200
    deliveries = r.get_json()
    assert len(deliveries) == 1
    assert deliveries[0]["event_type"] == "expense.created"
    assert deliveries[0]["status"] == "pending"

    captured = {}

    def fake_post(url, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data.decode("utf-8")
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response(204)

    monkeypatch.setattr("app.services.webhooks.requests.post", fake_post)

    r = client.post("/webhooks/deliveries/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["delivered"] == 1
    assert captured["url"] == "https://example.com/finmind-webhook"
    assert captured["headers"]["X-FinMind-Event"] == "expense.created"
    assert captured["headers"]["X-FinMind-Signature"] == sign_payload(
        "supersecret",
        captured["headers"]["X-FinMind-Timestamp"],
        captured["data"],
    )

    r = client.get("/webhooks/deliveries?status=delivered", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1


def test_webhook_delivery_retries_then_marks_failed(
    client, auth_header, app_fixture, monkeypatch
):
    _create_webhook(client, auth_header, event_types=["expense.created"])
    _create_expense(client, auth_header, description="Retry groceries")

    monkeypatch.setattr(
        "app.services.webhooks.requests.post",
        lambda *args, **kwargs: _Response(500),
    )

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        uid = delivery.user_id
        now = datetime.utcnow()

        first = process_due_deliveries(user_id=uid, now=now)
        assert first == {"processed": 1, "delivered": 0, "retrying": 1, "failed": 0}
        assert delivery.status == "pending"
        assert delivery.attempts == 1
        assert delivery.last_error == "HTTP 500"

        delivery.next_attempt_at = now
        db.session.commit()
        second = process_due_deliveries(user_id=uid, now=now)
        assert second["retrying"] == 1
        assert delivery.status == "pending"
        assert delivery.attempts == 2

        delivery.next_attempt_at = now
        db.session.commit()
        third = process_due_deliveries(user_id=uid, now=now)
        assert third == {"processed": 1, "delivered": 0, "retrying": 0, "failed": 1}
        assert delivery.status == "failed"
        assert delivery.attempts == 3


def test_webhook_event_filter_ignores_unsubscribed_events(client, auth_header):
    _create_webhook(client, auth_header, event_types=["bill.created"])
    _create_expense(client, auth_header)

    r = client.get("/webhooks/deliveries", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_webhook_rejects_unknown_event_type(client, auth_header):
    r = client.post(
        "/webhooks",
        json={
            "url": "https://example.com/finmind-webhook",
            "event_types": ["unknown.event"],
        },
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "unsupported event type" in r.get_json()["error"]
