import hmac
import hashlib

from app.extensions import db
from app.models import WebhookDelivery


class _FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_webhook_signed_delivery_and_event_types(client, auth_header, app_fixture, monkeypatch):
    captured = {}

    def _ok(req, timeout=5):
        captured["body"] = req.data.decode("utf-8")
        captured["event"] = req.headers.get("X-FinMind-Event")
        captured["sig"] = req.headers.get("X-FinMind-Signature")
        return _FakeResp()

    app_fixture.config.update(
        WEBHOOK_TARGET_URL="https://example.com/webhook",
        WEBHOOK_SIGNING_SECRET="secret123",
        WEBHOOK_MAX_RETRIES=3,
    )
    monkeypatch.setattr("app.services.webhooks.urlrequest.urlopen", _ok)

    r = client.post(
        "/expenses",
        json={"amount": 12.5, "description": "coffee", "date": "2026-01-01"},
        headers=auth_header,
    )
    assert r.status_code == 201

    assert captured["event"] == "expense.created"
    expected = hmac.new(
        b"secret123", captured["body"].encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert captured["sig"] == f"sha256={expected}"

    with app_fixture.app_context():
        row = db.session.query(WebhookDelivery).first()
        assert row is not None
        assert row.status == "sent"
        assert row.attempts == 1


def test_webhook_retries_and_failure_recorded(client, auth_header, app_fixture, monkeypatch):
    attempts = {"n": 0}

    def _fail(_req, timeout=5):
        attempts["n"] += 1
        raise OSError("network down")

    app_fixture.config.update(
        WEBHOOK_TARGET_URL="https://example.com/webhook",
        WEBHOOK_SIGNING_SECRET="secret123",
        WEBHOOK_MAX_RETRIES=3,
    )
    monkeypatch.setattr("app.services.webhooks.urlrequest.urlopen", _fail)

    r = client.post(
        "/reminders",
        json={"message": "x", "send_at": "2026-01-01T10:00:00", "channel": "email"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert attempts["n"] == 3

    with app_fixture.app_context():
        row = db.session.query(WebhookDelivery).first()
        assert row is not None
        assert row.status == "failed"
        assert row.attempts == 3


def test_webhook_event_types_documented(client):
    r = client.get("/docs/webhook-events")
    assert r.status_code == 200
    data = r.get_json()
    assert "event_types" in data
    assert "expense.created" in data["event_types"]
    assert "bill.created" in data["event_types"]
    assert "reminder.created" in data["event_types"]
