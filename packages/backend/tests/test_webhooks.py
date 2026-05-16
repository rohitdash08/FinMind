import threading
import time

from app.models import WebhookDeliveryLog, WebhookSubscription


def test_list_subscriptions_empty(client, auth_header):
    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_and_list_subscription(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_type": "expense.created"},
        headers=auth_header,
    )
    assert r.status_code == 201
    sub = r.get_json()
    assert sub["url"] == "https://example.com/hook"
    assert sub["event_type"] == "expense.created"
    assert sub["active"] is True
    assert "id" in sub

    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    subs = r.get_json()
    assert len(subs) == 1
    assert subs[0]["id"] == sub["id"]


def test_create_subscription_invalid_event_type(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_type": "invalid.event"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "invalid event_type" in r.get_json()["error"]


def test_create_subscription_missing_url(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"event_type": "expense.created"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "url required" in r.get_json()["error"]


def test_update_subscription(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_type": "expense.created"},
        headers=auth_header,
    )
    sub_id = r.get_json()["id"]

    r = client.patch(
        f"/webhooks/{sub_id}",
        json={"url": "https://example.com/hook2", "event_type": "bill.created", "active": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["url"] == "https://example.com/hook2"
    assert updated["event_type"] == "bill.created"
    assert updated["active"] is False


def test_update_subscription_not_found(client, auth_header):
    r = client.patch(
        "/webhooks/99999",
        json={"url": "https://example.com/hook"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_delete_subscription(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_type": "user.registered"},
        headers=auth_header,
    )
    sub_id = r.get_json()["id"]

    r = client.delete(f"/webhooks/{sub_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get("/webhooks", headers=auth_header)
    assert r.get_json() == []


def test_delete_subscription_not_found(client, auth_header):
    r = client.delete("/webhooks/99999", headers=auth_header)
    assert r.status_code == 404


def test_list_deliveries(client, auth_header, app_fixture):
    with app_fixture.app_context():
        from app.extensions import db
        sub = WebhookSubscription(user_id=1, url="https://example.com/hook", event_type="expense.created")
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

        log = WebhookDeliveryLog(
            subscription_id=sub_id,
            event_type="expense.created",
            attempt=1,
            status_code=200,
            success=True,
            error_message=None,
        )
        db.session.add(log)
        db.session.commit()

    r = client.get("/webhooks/deliveries", headers=auth_header)
    assert r.status_code == 200
    deliveries = r.get_json()
    assert len(deliveries) >= 1
    assert deliveries[0]["subscription_id"] == sub_id
    assert deliveries[0]["success"] is True


def test_expense_create_emits_webhook(client, auth_header, monkeypatch):
    emitted_events = []

    def fake_emit(event_type, payload, secret):
        emitted_events.append((event_type, payload))

    monkeypatch.setattr("app.routes.expenses.emit_event", fake_emit)

    cat_id = _create_category(client, auth_header)
    payload = {
        "amount": 42.0,
        "description": "Webhook test expense",
        "date": "2026-03-15",
        "category_id": cat_id,
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201

    assert len(emitted_events) >= 1
    event_type, event_payload = emitted_events[0]
    assert event_type == "expense.created"
    assert event_payload["amount"] == 42.0
    assert event_payload["description"] == "Webhook test expense"


def test_expense_delete_emits_webhook(client, auth_header, monkeypatch):
    emitted_events = []

    def fake_emit(event_type, payload, secret):
        emitted_events.append((event_type, payload))

    monkeypatch.setattr("app.routes.expenses.emit_event", fake_emit)

    payload = {
        "amount": 10.0,
        "description": "To be deleted",
        "date": "2026-03-15",
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    exp_id = r.get_json()["id"]

    emitted_events.clear()

    r = client.delete(f"/expenses/{exp_id}", headers=auth_header)
    assert r.status_code == 200

    assert len(emitted_events) >= 1
    event_type, event_payload = emitted_events[0]
    assert event_type == "expense.deleted"
    assert event_payload["id"] == exp_id


def test_bill_create_emits_webhook(client, auth_header, monkeypatch):
    emitted_events = []

    def fake_emit(event_type, payload, secret):
        emitted_events.append((event_type, payload))

    monkeypatch.setattr("app.routes.bills.emit_event", fake_emit)

    r = client.post(
        "/bills",
        json={"name": "Test Bill", "amount": 99.99, "next_due_date": "2026-04-01", "cadence": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 201

    assert len(emitted_events) >= 1
    event_type, event_payload = emitted_events[0]
    assert event_type == "bill.created"
    assert event_payload["name"] == "Test Bill"


def test_bill_pay_emits_webhook(client, auth_header, monkeypatch):
    emitted_events = []

    def fake_emit(event_type, payload, secret):
        emitted_events.append((event_type, payload))

    monkeypatch.setattr("app.routes.bills.emit_event", fake_emit)

    r = client.post(
        "/bills",
        json={"name": "Payable Bill", "amount": 50.0, "next_due_date": "2026-03-15", "cadence": "ONCE"},
        headers=auth_header,
    )
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    emitted_events.clear()

    r = client.post(f"/bills/{bill_id}/pay", headers=auth_header)
    assert r.status_code == 200

    assert len(emitted_events) >= 1
    event_type, event_payload = emitted_events[0]
    assert event_type == "bill.paid"
    assert event_payload["id"] == bill_id


def test_user_register_emits_webhook(client, auth_header, monkeypatch):
    emitted_events = []

    def fake_emit(event_type, payload, secret):
        emitted_events.append((event_type, payload))

    monkeypatch.setattr("app.routes.auth.emit_event", fake_emit)

    r = client.post("/auth/register", json={"email": "webhooktest@example.com", "password": "test123"})
    assert r.status_code == 201

    assert len(emitted_events) >= 1
    event_type, event_payload = emitted_events[0]
    assert event_type == "user.registered"
    assert event_payload["email"] == "webhooktest@example.com"


def test_delivery_retry_and_failure_logging(app_fixture, monkeypatch):
    import requests

    def fake_post(url, *args, **kwargs):
        raise requests.ConnectionError("fake connection error")

    monkeypatch.setattr("app.services.webhook.requests.post", fake_post)

    with app_fixture.app_context():
        from app.extensions import db
        from app.models import WebhookSubscription

        sub = WebhookSubscription(
            user_id=1, url="https://fail.example.com/hook", event_type="expense.created"
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

        from app.services.webhook import _dispatch_with_retry

        _dispatch_with_retry(sub, {"event_type": "expense.created", "id": 1, "amount": 5.0}, "test-secret")

        logs = db.session.query(WebhookDeliveryLog).filter_by(subscription_id=sub_id).order_by(
            WebhookDeliveryLog.id
        ).all()
        assert len(logs) == 3
        for log in logs:
            assert log.success is False
            assert log.error_message is not None


def test_hmac_signature_scheme():
    from app.services.webhook import _compute_signature

    sig = _compute_signature("mysecret", b'{"test": true}')
    assert len(sig) == 64
    assert isinstance(sig, str)

    sig2 = _compute_signature("mysecret", b'{"test": true}')
    assert sig == sig2

    sig3 = _compute_signature("wrong", b'{"test": true}')
    assert sig != sig3


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    return r.get_json()[0]["id"]
