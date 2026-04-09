from datetime import datetime, timedelta

from app.extensions import db
from app.models import WebhookDelivery, WebhookDeliveryStatus, WebhookEvent
from app.services import webhooks as webhooks_service


def _create_subscription(client, auth_header, events=None, target_url="https://example.com/hook"):
    payload = {
        "target_url": target_url,
        "secret": "whsec_test_123",
        "description": "integration",
        "subscribed_events": events or ["expense.created"],
    }
    response = client.post("/webhooks", json=payload, headers=auth_header)
    assert response.status_code == 201
    return response.get_json()


def test_create_webhook_subscription_and_list(client, auth_header):
    created = _create_subscription(client, auth_header)
    assert created["target_url"] == "https://example.com/hook"
    assert "secret" not in created

    response = client.get("/webhooks", headers=auth_header)
    assert response.status_code == 200
    items = response.get_json()
    assert len(items) == 1
    assert items[0]["subscribed_events"] == ["expense.created"]


def test_create_webhook_subscription_rejects_invalid_input(client, auth_header):
    response = client.post(
        "/webhooks",
        json={"target_url": "notaurl", "secret": "x", "subscribed_events": ["expense.created"]},
        headers=auth_header,
    )
    assert response.status_code == 400

    response = client.post(
        "/webhooks",
        json={"target_url": "https://example.com", "secret": "x", "subscribed_events": ["nope"]},
        headers=auth_header,
    )
    assert response.status_code == 400


def test_expense_created_emits_webhook_event_and_delivery(client, auth_header):
    _create_subscription(client, auth_header, events=["expense.created"])

    response = client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Lunch", "date": "2026-04-09"},
        headers=auth_header,
    )
    assert response.status_code == 201

    with client.application.app_context():
        event = db.session.query(WebhookEvent).filter_by(event_type="expense.created").one()
        delivery = db.session.query(WebhookDelivery).filter_by(event_id=event.id).one()
        assert event.resource_type == "expense"
        assert event.payload_json["type"] == "expense.created"
        assert event.payload_json["data"]["description"] == "Lunch"
        assert delivery.status == WebhookDeliveryStatus.PENDING.value


def test_event_filtering_only_matching_subscriptions_receive_delivery(client, auth_header):
    _create_subscription(client, auth_header, events=["bill.paid"])

    response = client.post(
        "/expenses",
        json={"amount": 15, "description": "Taxi", "date": "2026-04-09"},
        headers=auth_header,
    )
    assert response.status_code == 201

    with client.application.app_context():
        assert db.session.query(WebhookEvent).filter_by(event_type="expense.created").count() == 1
        assert db.session.query(WebhookDelivery).count() == 0


def test_sign_payload_is_stable():
    payload = {"b": 2, "a": 1}
    raw = webhooks_service.serialize_payload(payload)
    signature = webhooks_service.sign_payload("secret", "123", raw)
    assert raw == '{"a":1,"b":2}'
    assert signature == "sha256=194ce64d4e136cb0e4ea6b5306a3efd27755da6a9d57e25dd61892b6d2b7857f"


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_run_pending_deliveries_marks_success_on_2xx(client, auth_header, monkeypatch):
    _create_subscription(client, auth_header, events=["expense.created"])
    client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Lunch", "date": "2026-04-09"},
        headers=auth_header,
    )

    monkeypatch.setattr(webhooks_service.requests, "post", lambda *args, **kwargs: _FakeResponse(200))

    with client.application.app_context():
        result = webhooks_service.run_pending_deliveries()
        assert result["succeeded"] == 1
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == WebhookDeliveryStatus.SUCCEEDED.value
        assert delivery.attempt_count == 1
        assert delivery.last_response_code == 200


def test_run_pending_deliveries_schedules_retry_on_failure(client, auth_header, monkeypatch):
    _create_subscription(client, auth_header, events=["expense.created"])
    client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Lunch", "date": "2026-04-09"},
        headers=auth_header,
    )

    monkeypatch.setattr(webhooks_service.requests, "post", lambda *args, **kwargs: _FakeResponse(500))

    with client.application.app_context():
        result = webhooks_service.run_pending_deliveries()
        assert result["retried"] == 1
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == WebhookDeliveryStatus.RETRY_SCHEDULED.value
        assert delivery.attempt_count == 1
        assert delivery.next_attempt_at is not None


def test_run_pending_deliveries_marks_failed_after_max_attempts(client, auth_header, monkeypatch):
    _create_subscription(client, auth_header, events=["expense.created"])
    client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Lunch", "date": "2026-04-09"},
        headers=auth_header,
    )

    monkeypatch.setattr(webhooks_service.requests, "post", lambda *args, **kwargs: _FakeResponse(500))

    with client.application.app_context():
        delivery = db.session.query(WebhookDelivery).one()
        delivery.status = WebhookDeliveryStatus.RETRY_SCHEDULED.value
        delivery.attempt_count = webhooks_service.MAX_ATTEMPTS - 1
        delivery.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

        result = webhooks_service.run_pending_deliveries()
        assert result["failed"] == 1
        delivery = db.session.query(WebhookDelivery).one()
        assert delivery.status == WebhookDeliveryStatus.FAILED.value
        assert delivery.attempt_count == webhooks_service.MAX_ATTEMPTS


def test_reminder_sent_event_emitted_only_on_successful_send(client, auth_header, monkeypatch):
    reminder = client.post(
        "/reminders",
        json={
            "message": "Pay credit card",
            "send_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "channel": "email",
        },
        headers=auth_header,
    )
    assert reminder.status_code == 201

    monkeypatch.setattr("app.routes.reminders.send_reminder", lambda _r: False)
    response = client.post("/reminders/run", headers=auth_header)
    assert response.status_code == 200
    with client.application.app_context():
        assert db.session.query(WebhookEvent).filter_by(event_type="reminder.sent").count() == 0

    _create_subscription(client, auth_header, events=["reminder.sent"])
    monkeypatch.setattr("app.routes.reminders.send_reminder", lambda _r: True)
    response = client.post("/reminders/run", headers=auth_header)
    assert response.status_code == 200
    with client.application.app_context():
        assert db.session.query(WebhookEvent).filter_by(event_type="reminder.sent").count() == 1
