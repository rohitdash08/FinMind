"""Tests for webhook event system."""

import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock


def test_create_webhook_endpoint(client, auth_header):
    r = client.post("/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["expense.created", "expense.deleted"],
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["url"] == "https://example.com/hook"
    assert "secret" in data  # secret shown on creation
    assert len(data["secret"]) == 64  # hex of 32 bytes
    assert data["events"] == ["expense.created", "expense.deleted"]


def test_create_webhook_requires_https(client, auth_header):
    r = client.post("/webhooks", json={
        "url": "http://insecure.com/hook",
        "events": ["*"],
    }, headers=auth_header)
    assert r.status_code == 400
    assert "HTTPS" in r.get_json()["error"]


def test_create_webhook_invalid_event(client, auth_header):
    r = client.post("/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["invalid.event"],
    }, headers=auth_header)
    assert r.status_code == 400


def test_list_webhooks(client, auth_header):
    client.post("/webhooks", json={
        "url": "https://a.com/hook", "events": ["*"]
    }, headers=auth_header)
    client.post("/webhooks", json={
        "url": "https://b.com/hook", "events": ["*"]
    }, headers=auth_header)

    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_update_webhook(client, auth_header):
    r = client.post("/webhooks", json={
        "url": "https://old.com/hook", "events": ["*"]
    }, headers=auth_header)
    eid = r.get_json()["id"]

    r = client.patch(f"/webhooks/{eid}", json={
        "url": "https://new.com/hook",
        "is_active": False,
    }, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["url"] == "https://new.com/hook"
    assert r.get_json()["is_active"] is False


def test_delete_webhook(client, auth_header):
    r = client.post("/webhooks", json={
        "url": "https://gone.com/hook", "events": ["*"]
    }, headers=auth_header)
    eid = r.get_json()["id"]

    r = client.delete(f"/webhooks/{eid}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/webhooks", headers=auth_header)
    assert len(r.get_json()) == 0


def test_list_event_types(client, auth_header):
    r = client.get("/webhooks/events", headers=auth_header)
    assert r.status_code == 200
    events = r.get_json()["events"]
    assert len(events) > 0
    types = [e["type"] for e in events]
    assert "expense.created" in types
    assert "bill.created" in types


def test_emit_event_delivers_with_signature(client, auth_header):
    """Test that emitting an event creates a signed delivery."""
    # Create endpoint
    r = client.post("/webhooks", json={
        "url": "https://test.com/hook",
        "events": ["expense.created"],
    }, headers=auth_header)
    data = r.get_json()
    eid = data["id"]
    secret = data["secret"]

    # Mock the HTTP request
    with patch("app.services.webhooks.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        from app.services.webhooks import emit_event
        # Need app context for this
        with client.application.app_context():
            delivery_ids = emit_event(
                user_id=1,  # test user
                event_type="expense.created",
                data={"id": 42, "amount": 10.5},
            )

        assert len(delivery_ids) == 1

        # Verify signature
        call_kwargs = mock_post.call_args
        sent_payload = call_kwargs.kwargs.get("data") or call_kwargs[1].get("data")
        sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")

        expected_sig = hmac.new(
            secret.encode(), sent_payload.encode(), hashlib.sha256
        ).hexdigest()
        assert sent_headers["X-FinMind-Signature"] == f"sha256={expected_sig}"
        assert sent_headers["X-FinMind-Event"] == "expense.created"

    # Check delivery history
    r = client.get(f"/webhooks/{eid}/deliveries", headers=auth_header)
    assert r.status_code == 200
    deliveries = r.get_json()
    assert len(deliveries) == 1
    assert deliveries[0]["success"] is True


def test_webhooks_unauthorized(client):
    r = client.get("/webhooks")
    assert r.status_code in (401, 422)
