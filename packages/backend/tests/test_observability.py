from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User, WebhookDelivery, WebhookTarget
from app.services.webhooks import WebhookService


def _direct_auth_header(client) -> dict[str, str]:
    with client.application.app_context():
        user = User(
            email="direct-observability@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def test_request_id_header_is_returned(client):
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert len(request_id) >= 16


def test_metrics_endpoint_exposes_http_and_reminder_metrics(client, auth_header):
    # Trigger baseline API traffic.
    health = client.get("/health")
    assert health.status_code == 200

    # Trigger reminder scheduling flow to populate product KPI counters.
    bill = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 59.0,
            "next_due_date": "2026-03-20",
            "cadence": "MONTHLY",
            "channel_email": True,
            "channel_whatsapp": False,
            "autopay_enabled": False,
        },
        headers=auth_header,
    )
    assert bill.status_code == 201
    bill_id = bill.get_json()["id"]

    scheduled = client.post(f"/reminders/bills/{bill_id}/schedule", headers=auth_header)
    assert scheduled.status_code == 200
    assert scheduled.get_json()["created"] >= 1

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    payload = metrics.get_data(as_text=True)
    assert "finmind_http_requests_total" in payload
    assert 'endpoint="/health"' in payload
    assert "finmind_reminder_events_total" in payload
    assert 'event="scheduled"' in payload


def test_metrics_endpoint_exposes_webhook_retry_metrics(client, monkeypatch):
    def _always_fail(*_args, **_kwargs):
        import requests

        raise requests.RequestException("boom")

    monkeypatch.setattr("app.services.webhooks.requests.post", _always_fail)

    with client.application.app_context():
        user = User(
            email="metrics-webhooks@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.flush()

        target = WebhookTarget(
            user_id=user.id,
            url="https://example.test/webhook",
            secret="super-secret-key",
            enabled=True,
            events=["expense.created"],
        )
        db.session.add(target)
        db.session.flush()

        db.session.add(
            WebhookDelivery(
                target_id=target.id,
                event_type="expense.created",
                payload={"type": "expense.created", "data": {"id": 1}},
                status="pending",
                attempt_count=0,
            )
        )
        db.session.commit()

        processed = WebhookService.process_pending_deliveries()
        assert processed == 1

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    payload = metrics.get_data(as_text=True)
    assert "finmind_webhook_delivery_events_total" in payload
    assert 'result="retry_scheduled"' in payload
    assert 'event_type="expense.created"' in payload
