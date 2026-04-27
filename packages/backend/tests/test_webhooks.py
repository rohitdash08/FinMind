import hashlib
import hmac
import json
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.extensions import db
from app.models import Webhook, WebhookDelivery, WebhookDeliveryStatus
from app.services import webhooks as webhook_service


@pytest.fixture()
def webhook_url():
    return "https://example.test/hook"


def _ok_response(status: int = 200):
    response = MagicMock()
    response.status_code = status
    return response


def test_event_types_listed_publicly(client):
    r = client.get("/webhooks/events")
    assert r.status_code == 200
    events = r.get_json()["events"]
    assert "expense.created" in events
    assert "bill.paid" in events


def test_register_webhook_returns_secret_then_lists_without_it(client, auth_header, webhook_url):
    r = client.post(
        "/webhooks",
        json={"url": webhook_url, "events": ["expense.created"]},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["secret"]
    assert body["events"] == ["expense.created"]

    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert "secret" not in items[0]


def test_register_rejects_invalid_url_and_events(client, auth_header):
    r = client.post(
        "/webhooks", json={"url": "ftp://nope"}, headers=auth_header
    )
    assert r.status_code == 400

    r = client.post(
        "/webhooks",
        json={"url": "https://example.test/hook", "events": ["bogus.event"]},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_signature_can_be_verified_by_receiver(client, auth_header, app_fixture, webhook_url):
    r = client.post(
        "/webhooks", json={"url": webhook_url}, headers=auth_header
    )
    secret = r.get_json()["secret"]

    captured: dict = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return _ok_response()

    with patch.object(webhook_service.requests, "post", side_effect=fake_post):
        r = client.post(
            "/expenses",
            json={"amount": 10.0, "description": "coffee", "date": date.today().isoformat()},
            headers=auth_header,
        )
        assert r.status_code == 201

    body = captured["data"]
    sig = captured["headers"][webhook_service.SIGNATURE_HEADER]
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sig == expected
    assert captured["headers"][webhook_service.EVENT_HEADER] == "expense.created"
    envelope = json.loads(body.decode())
    assert envelope["type"] == "expense.created"
    assert envelope["data"]["description"] == "coffee"

    with app_fixture.app_context():
        deliveries = db.session.query(WebhookDelivery).all()
        assert len(deliveries) == 1
        assert deliveries[0].status == WebhookDeliveryStatus.SUCCESS.value
        assert deliveries[0].attempts == 1


def test_failed_delivery_is_retried_then_marked_failed(client, auth_header, app_fixture, webhook_url):
    client.post("/webhooks", json={"url": webhook_url}, headers=auth_header)

    # First attempt fails on emission.
    with patch.object(
        webhook_service.requests, "post",
        side_effect=requests.ConnectionError("boom"),
    ):
        client.post(
            "/expenses",
            json={"amount": 1.0, "description": "x", "date": date.today().isoformat()},
            headers=auth_header,
        )

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == WebhookDeliveryStatus.PENDING.value
        assert delivery.attempts == 1
        assert delivery.last_error
        # Force the retry window to elapse so /run picks it up.
        delivery.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        delivery_id = delivery.id

    # Drive enough retries to exhaust MAX_ATTEMPTS.
    with patch.object(
        webhook_service.requests, "post",
        side_effect=requests.ConnectionError("still down"),
    ):
        for _ in range(webhook_service.MAX_ATTEMPTS):
            with app_fixture.app_context():
                d = db.session.get(WebhookDelivery, delivery_id)
                if d.status != WebhookDeliveryStatus.PENDING.value:
                    break
                d.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
                db.session.commit()
            r = client.post("/webhooks/run", headers=auth_header)
            assert r.status_code == 200

    with app_fixture.app_context():
        delivery = db.session.get(WebhookDelivery, delivery_id)
        assert delivery.status == WebhookDeliveryStatus.FAILED.value
        assert delivery.attempts == webhook_service.MAX_ATTEMPTS


def test_retry_eventually_succeeds(client, auth_header, app_fixture, webhook_url):
    client.post("/webhooks", json={"url": webhook_url}, headers=auth_header)

    with patch.object(
        webhook_service.requests, "post",
        side_effect=requests.ConnectionError("temporary"),
    ):
        client.post(
            "/expenses",
            json={"amount": 1.0, "description": "x", "date": date.today().isoformat()},
            headers=auth_header,
        )

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        delivery.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

    with patch.object(webhook_service.requests, "post", return_value=_ok_response()):
        r = client.post("/webhooks/run", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["delivered"] == 1

    with app_fixture.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == WebhookDeliveryStatus.SUCCESS.value


def test_event_filter_skips_unsubscribed_events(client, auth_header, webhook_url):
    client.post(
        "/webhooks",
        json={"url": webhook_url, "events": ["bill.paid"]},
        headers=auth_header,
    )
    with patch.object(webhook_service.requests, "post", return_value=_ok_response()) as mock_post:
        r = client.post(
            "/expenses",
            json={"amount": 5.0, "description": "y", "date": date.today().isoformat()},
            headers=auth_header,
        )
        assert r.status_code == 201
        mock_post.assert_not_called()


def test_inactive_webhook_does_not_fire(client, auth_header, webhook_url):
    r = client.post("/webhooks", json={"url": webhook_url}, headers=auth_header)
    hook_id = r.get_json()["id"]
    r = client.patch(
        f"/webhooks/{hook_id}", json={"active": False}, headers=auth_header
    )
    assert r.status_code == 200

    with patch.object(webhook_service.requests, "post", return_value=_ok_response()) as mock_post:
        client.post(
            "/expenses",
            json={"amount": 5.0, "description": "z", "date": date.today().isoformat()},
            headers=auth_header,
        )
        mock_post.assert_not_called()


def test_delete_webhook_removes_it(client, auth_header, webhook_url):
    r = client.post("/webhooks", json={"url": webhook_url}, headers=auth_header)
    hook_id = r.get_json()["id"]
    r = client.delete(f"/webhooks/{hook_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get("/webhooks", headers=auth_header)
    assert r.get_json() == []


def test_user_isolation(client, auth_header, app_fixture, webhook_url):
    # User A creates a webhook
    client.post("/webhooks", json={"url": webhook_url}, headers=auth_header)

    # Register a second user
    email, password = "other@example.com", "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201)
    r = client.post("/auth/login", json={"email": email, "password": password})
    other_header = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.get("/webhooks", headers=other_header)
    assert r.get_json() == []


def test_verify_signature_helper():
    body = b'{"hello":"world"}'
    secret = "topsecret"
    sig = webhook_service.sign_payload(secret, body)
    assert webhook_service.verify_signature(secret, body, sig) is True
    assert webhook_service.verify_signature(secret, body, "sha256=bad") is False
