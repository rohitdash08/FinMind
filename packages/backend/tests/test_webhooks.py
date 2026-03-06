import json
import pytest
from datetime import datetime
from unittest.mock import patch, Mock
from app.models import (
    WebhookEndpoint,
    WebhookEvent,
    WebhookDelivery,
    WebhookEventType,
    WebhookDeliveryStatus,
)
from app.services.webhooks import (
    emit_webhook_event,
    compute_signature,
    retry_failed_webhooks,
    get_delivery_stats,
)


@pytest.fixture
def webhook_endpoint(client, auth_header):
    response = client.post(
        "/webhooks",
        headers=auth_header,
        json={
            "url": "https://example.com/webhook",
            "events": ["expense.created", "bill.paid"],
        },
    )
    assert response.status_code == 201
    return response.get_json()


def test_create_webhook_endpoint(client, auth_header):
    response = client.post(
        "/webhooks",
        headers=auth_header,
        json={
            "url": "https://example.com/webhook",
            "events": ["expense.created", "bill.created"],
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["url"] == "https://example.com/webhook"
    assert data["active"] is True
    assert "secret" in data
    assert len(data["secret"]) > 20


def test_create_webhook_invalid_url(client, auth_header):
    response = client.post(
        "/webhooks",
        headers=auth_header,
        json={
            "url": "not-a-valid-url",
            "events": ["expense.created"],
        },
    )
    assert response.status_code == 400


def test_create_webhook_no_events(client, auth_header):
    response = client.post(
        "/webhooks",
        headers=auth_header,
        json={
            "url": "https://example.com/webhook",
            "events": [],
        },
    )
    assert response.status_code == 400


def test_list_webhooks(client, auth_header, webhook_endpoint):
    response = client.get("/webhooks", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) >= 1
    assert data[0]["id"] == webhook_endpoint["id"]


def test_get_webhook(client, auth_header, webhook_endpoint):
    response = client.get(
        f"/webhooks/{webhook_endpoint['id']}", headers=auth_header
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == webhook_endpoint["id"]


def test_update_webhook(client, auth_header, webhook_endpoint):
    response = client.patch(
        f"/webhooks/{webhook_endpoint['id']}",
        headers=auth_header,
        json={
            "url": "https://newexample.com/webhook",
            "events": ["*"],
            "active": False,
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["url"] == "https://newexample.com/webhook"
    assert data["active"] is False
    assert "*" in data["events"]


def test_delete_webhook(client, auth_header, webhook_endpoint):
    response = client.delete(
        f"/webhooks/{webhook_endpoint['id']}", headers=auth_header
    )
    assert response.status_code == 204

    response = client.get(
        f"/webhooks/{webhook_endpoint['id']}", headers=auth_header
    )
    assert response.status_code == 404


def test_regenerate_secret(client, auth_header, webhook_endpoint):
    old_secret = webhook_endpoint["secret"]
    response = client.post(
        f"/webhooks/{webhook_endpoint['id']}/regenerate-secret",
        headers=auth_header,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["secret"] != old_secret
    assert len(data["secret"]) > 20


@patch("app.services.webhooks.requests.post")
def test_emit_webhook_event_success(mock_post, app, user, webhook_endpoint):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_post.return_value = mock_response

    with app.app_context():
        event = emit_webhook_event(
            user.id,
            WebhookEventType.EXPENSE_CREATED,
            {"id": 1, "amount": 100, "notes": "Test"},
        )

        assert event is not None
        assert event.user_id == user.id
        assert event.event_type == WebhookEventType.EXPENSE_CREATED

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "X-FinMind-Signature" in call_args.kwargs["headers"]
        assert "X-FinMind-Event" in call_args.kwargs["headers"]


@patch("app.services.webhooks.requests.post")
def test_webhook_delivery_retry(mock_post, app, user, webhook_endpoint):
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    with app.app_context():
        event = emit_webhook_event(
            user.id,
            WebhookEventType.BILL_CREATED,
            {"id": 1, "name": "Rent"},
        )

        from app.extensions import db

        delivery = (
            db.session.query(WebhookDelivery).filter_by(event_id=event.id).first()
        )
        assert delivery is not None
        assert delivery.status in [
            WebhookDeliveryStatus.PENDING,
            WebhookDeliveryStatus.RETRYING,
        ]
        assert delivery.attempt_count > 0
        assert delivery.next_retry_at is not None


def test_compute_signature():
    payload = '{"test": "data"}'
    secret = "my-secret-key"
    signature = compute_signature(payload, secret)

    assert len(signature) == 64
    assert signature == compute_signature(payload, secret)

    different_signature = compute_signature(payload, "different-secret")
    assert signature != different_signature


def test_webhook_event_filtering(app, user):
    from app.extensions import db

    endpoint1 = WebhookEndpoint(
        user_id=user.id,
        url="https://example1.com/webhook",
        secret="secret1",
        events=json.dumps(["expense.created"]),
        active=True,
    )
    endpoint2 = WebhookEndpoint(
        user_id=user.id,
        url="https://example2.com/webhook",
        secret="secret2",
        events=json.dumps(["bill.paid"]),
        active=True,
    )
    db.session.add_all([endpoint1, endpoint2])
    db.session.commit()

    with patch("app.services.webhooks.requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        emit_webhook_event(
            user.id, WebhookEventType.EXPENSE_CREATED, {"id": 1, "amount": 50}
        )

        assert mock_post.call_count == 1


def test_webhook_wildcard_subscription(app, user):
    from app.extensions import db

    endpoint = WebhookEndpoint(
        user_id=user.id,
        url="https://example.com/webhook",
        secret="secret",
        events=json.dumps(["*"]),
        active=True,
    )
    db.session.add(endpoint)
    db.session.commit()

    with patch("app.services.webhooks.requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        emit_webhook_event(
            user.id, WebhookEventType.EXPENSE_CREATED, {"id": 1}
        )
        emit_webhook_event(user.id, WebhookEventType.BILL_PAID, {"id": 2})

        assert mock_post.call_count == 2


def test_list_webhook_events(client, auth_header, webhook_endpoint):
    response = client.post(
        "/expenses",
        headers=auth_header,
        json={
            "amount": 100,
            "description": "Test expense",
            "date": "2024-01-01",
        },
    )
    assert response.status_code == 201

    response = client.get("/webhooks/events", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_get_webhook_stats(client, auth_header, webhook_endpoint):
    response = client.get("/webhooks/stats", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert "total_events" in data
    assert "total_deliveries" in data
    assert "successful_deliveries" in data
    assert "failed_deliveries" in data
    assert "pending_deliveries" in data


def test_retry_failed_webhooks_endpoint(client, auth_header):
    response = client.post("/webhooks/retry", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert "retried" in data
