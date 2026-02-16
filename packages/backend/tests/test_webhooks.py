"""Tests for the Webhook Event System.

Covers:
- Subscription CRUD (create, list, update, delete)
- Signature verification
- Event emission and domain event creation
- Delivery log tracking
- Retry & dead-letter logic
- Auto-disable after repeated failures
- Test ping endpoint
- Event types listing
- Delivery metrics
- Edge cases
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from app.models import (
    WebhookDeliveryLog,
    WebhookEvent,
    WebhookSubscription,
)
from app.services.webhook import (
    AUTO_DISABLE_THRESHOLD,
    MAX_ATTEMPTS,
    SUPPORTED_EVENT_TYPES,
    compute_signature,
    emit_event,
    generate_secret,
    process_event_queue,
    process_retries,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_subscription(
    client, auth_header, url="https://example.com/hook", events=None
):
    payload = {
        "url": url,
        "event_types": events or ["expense.created"],
    }
    return client.post("/webhooks", json=payload, headers=auth_header)


# ---------------------------------------------------------------------------
# Subscription CRUD
# ---------------------------------------------------------------------------


def test_create_subscription(client, auth_header):
    r = _create_subscription(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["url"] == "https://example.com/hook"
    assert data["active"] is True
    assert "secret" in data
    assert len(data["secret"]) == 64  # 32-byte hex


def test_create_subscription_missing_url(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"event_types": ["expense.created"]},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_subscription_invalid_event_type(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["invalid.type"]},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "unsupported" in r.get_json()["error"]


def test_create_subscription_wildcard(client, auth_header):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["*"]},
        headers=auth_header,
    )
    assert r.status_code == 201


def test_list_subscriptions(client, auth_header):
    _create_subscription(client, auth_header, url="https://a.com/hook")
    _create_subscription(client, auth_header, url="https://b.com/hook")
    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 2
    assert "secret" not in data[0]  # secret not returned on list


def test_update_subscription(client, auth_header):
    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    r = client.patch(
        f"/webhooks/{sub_id}",
        json={"url": "https://updated.com/hook", "active": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["url"] == "https://updated.com/hook"
    assert data["active"] is False


def test_update_subscription_reactivate_resets_failures(client, auth_header):
    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    # Simulate failures
    with client.application.app_context():
        sub = db.session.get(WebhookSubscription, sub_id)
        sub.consecutive_failures = 5
        sub.active = False
        db.session.commit()

    r = client.patch(
        f"/webhooks/{sub_id}",
        json={"active": True},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["active"] is True
    assert data["consecutive_failures"] == 0


def test_update_nonexistent_subscription(client, auth_header):
    r = client.patch(
        "/webhooks/9999",
        json={"url": "https://x.com"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_delete_subscription(client, auth_header):
    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    r = client.delete(f"/webhooks/{sub_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/webhooks", headers=auth_header)
    ids = [s["id"] for s in r.get_json()]
    assert sub_id not in ids


def test_delete_nonexistent_subscription(client, auth_header):
    r = client.delete("/webhooks/9999", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


def test_generate_secret_length():
    secret = generate_secret()
    assert len(secret) == 64


def test_compute_signature_correctness():
    secret = "abc123"
    timestamp = "1700000000"
    payload = '{"event":"test"}'
    sig = compute_signature(secret, timestamp, payload)

    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected


def test_signature_changes_with_different_payload():
    secret = "secret"
    ts = "1700000000"
    sig1 = compute_signature(secret, ts, '{"a":1}')
    sig2 = compute_signature(secret, ts, '{"a":2}')
    assert sig1 != sig2


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


def test_emit_event_creates_record(app_fixture):
    with app_fixture.app_context():
        event = emit_event(1, "expense.created", {"id": 1, "amount": 50.0})
        assert event.id is not None
        assert event.event_type == "expense.created"
        assert event.event_version == "1"
        assert len(event.correlation_id) == 36

        stored = db.session.get(WebhookEvent, event.id)
        assert stored is not None
        assert json.loads(stored.payload)["amount"] == 50.0


def test_emit_event_custom_version(app_fixture):
    with app_fixture.app_context():
        event = emit_event(1, "expense.created", {"id": 1}, event_version="2")
        assert event.event_version == "2"


def test_emit_event_unique_correlation_ids(app_fixture):
    with app_fixture.app_context():
        e1 = emit_event(1, "expense.created", {"id": 1})
        e2 = emit_event(1, "expense.created", {"id": 2})
        assert e1.correlation_id != e2.correlation_id


# ---------------------------------------------------------------------------
# Event dispatch & delivery
# ---------------------------------------------------------------------------


@patch("app.services.webhook.http_requests.post")
def test_process_event_queue_delivers(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        event = emit_event(1, "expense.created", {"id": 1, "amount": 10})
        process_event_queue()

        assert mock_post.called
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert "X-FinMind-Signature" in headers
        assert "X-FinMind-Event-Version" in headers
        assert headers["X-FinMind-Event"] == "expense.created"
        assert headers["X-FinMind-Correlation-Id"] == event.correlation_id

        log = db.session.query(WebhookDeliveryLog).filter_by(event_id=event.id).first()
        assert log is not None
        assert log.status == "delivered"
        assert log.latency_ms is not None


@patch("app.services.webhook.http_requests.post")
def test_event_not_delivered_to_unmatched_subscription(mock_post, app_fixture):
    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["bill.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        assert not mock_post.called


@patch("app.services.webhook.http_requests.post")
def test_wildcard_subscription_receives_all_events(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["*"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "bill.paid", {"id": 1})
        process_event_queue()

        assert mock_post.called


@patch("app.services.webhook.http_requests.post")
def test_inactive_subscription_skipped(mock_post, app_fixture):
    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=False,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        assert not mock_post.called


# ---------------------------------------------------------------------------
# Failure, retry, dead-letter
# ---------------------------------------------------------------------------


@patch("app.services.webhook.http_requests.post")
def test_failed_delivery_schedules_retry(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        log = db.session.query(WebhookDeliveryLog).first()
        assert log.status == "pending"
        assert log.failure_class == "http_5xx"
        assert log.next_retry_at is not None

        sub_after = db.session.get(WebhookSubscription, sub.id)
        assert sub_after.consecutive_failures == 1


@patch("app.services.webhook.http_requests.post")
def test_timeout_failure_classification(mock_post, app_fixture):
    import requests as real_requests

    mock_post.side_effect = real_requests.Timeout("timed out")

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        log = db.session.query(WebhookDeliveryLog).first()
        assert log.failure_class == "timeout"


@patch("app.services.webhook.http_requests.post")
def test_connection_error_classification(mock_post, app_fixture):
    import requests as real_requests

    mock_post.side_effect = real_requests.ConnectionError("refused")

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        log = db.session.query(WebhookDeliveryLog).first()
        assert log.failure_class == "connection_error"


@patch("app.services.webhook.http_requests.post")
def test_dead_letter_after_max_attempts(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "error"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        # Simulate max attempts reached
        log = db.session.query(WebhookDeliveryLog).first()
        log.attempt = MAX_ATTEMPTS
        log.next_retry_at = None
        db.session.commit()

        # Manually set up for retry
        from datetime import datetime

        log.next_retry_at = datetime.utcnow()
        log.status = "pending"
        db.session.commit()

        process_retries()

        db.session.refresh(log)
        assert log.status == "dead_letter"


@patch("app.services.webhook.http_requests.post")
def test_auto_disable_after_threshold(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "error"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
            consecutive_failures=AUTO_DISABLE_THRESHOLD - 1,
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        # Query fresh from DB to avoid identity-map staleness
        db.session.expire_all()
        refreshed = db.session.get(WebhookSubscription, sub_id)
        assert refreshed.active is False
        assert refreshed.disabled_at is not None
        assert refreshed.consecutive_failures == AUTO_DISABLE_THRESHOLD

        log = db.session.query(WebhookDeliveryLog).first()
        assert log.status == "dead_letter"


@patch("app.services.webhook.http_requests.post")
def test_successful_delivery_resets_failures(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
            consecutive_failures=5,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        db.session.refresh(sub)
        assert sub.consecutive_failures == 0


@patch("app.services.webhook.http_requests.post")
def test_http_4xx_failure_classification(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        sub = WebhookSubscription(
            user_id=1,
            url="https://example.com/hook",
            secret=generate_secret(),
            event_types=json.dumps(["expense.created"]),
            active=True,
        )
        db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        log = db.session.query(WebhookDeliveryLog).first()
        assert log.failure_class == "http_4xx"


# ---------------------------------------------------------------------------
# Delivery logs endpoint
# ---------------------------------------------------------------------------


@patch("app.services.webhook.http_requests.post")
def test_list_deliveries(mock_post, client, auth_header, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    with app_fixture.app_context():
        sub = db.session.get(WebhookSubscription, sub_id)
        uid = sub.user_id
        emit_event(uid, "expense.created", {"id": 1})
        process_event_queue()

    r = client.get(f"/webhooks/{sub_id}/deliveries", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 1
    assert "correlation_id" in data[0]
    assert "latency_ms" in data[0]
    assert "failure_class" in data[0]


# ---------------------------------------------------------------------------
# Test ping
# ---------------------------------------------------------------------------


@patch("app.services.webhook.http_requests.post")
def test_ping_success(mock_post, client, auth_header):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "pong"
    mock_post.return_value = mock_resp

    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    r = client.post(f"/webhooks/{sub_id}/test", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["status_code"] == 200
    assert "latency_ms" in data


@patch("app.services.webhook.http_requests.post")
def test_ping_failure(mock_post, client, auth_header):
    import requests as real_requests

    mock_post.side_effect = real_requests.ConnectionError("refused")

    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    r = client.post(f"/webhooks/{sub_id}/test", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is False
    assert data["error"] == "connection_error"


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


def test_list_event_types(client, auth_header):
    r = client.get("/webhooks/event-types", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert set(SUPPORTED_EVENT_TYPES).issubset(set(data["event_types"]))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@patch("app.services.webhook.http_requests.post")
def test_metrics_endpoint(mock_post, client, auth_header, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    r = _create_subscription(client, auth_header)
    sub_id = r.get_json()["id"]

    with app_fixture.app_context():
        sub = db.session.get(WebhookSubscription, sub_id)
        emit_event(sub.user_id, "expense.created", {"id": 1})
        process_event_queue()

    r = client.get("/webhooks/metrics", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_deliveries"] >= 1
    assert data["delivered"] >= 1
    assert "avg_latency_ms" in data
    assert "failure_breakdown" in data


def test_metrics_empty(client, auth_header):
    r = client.get("/webhooks/metrics", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_deliveries"] == 0


# ---------------------------------------------------------------------------
# N+1 avoidance: multiple subscriptions, single event
# ---------------------------------------------------------------------------


@patch("app.services.webhook.http_requests.post")
def test_batch_dispatch_avoids_n_plus_one(mock_post, app_fixture):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    with app_fixture.app_context():
        for i in range(3):
            sub = WebhookSubscription(
                user_id=1,
                url=f"https://hook{i}.example.com/wh",
                secret=generate_secret(),
                event_types=json.dumps(["expense.created"]),
                active=True,
            )
            db.session.add(sub)
        db.session.commit()

        emit_event(1, "expense.created", {"id": 1})
        process_event_queue()

        # All 3 subscriptions should receive the event
        assert mock_post.call_count == 3


# ---------------------------------------------------------------------------
# Integration: event emitted from expense route
# ---------------------------------------------------------------------------


def test_expense_create_emits_event(client, auth_header, app_fixture):
    _create_subscription(client, auth_header, events=["expense.created"])

    r = client.post(
        "/expenses",
        json={
            "amount": 25.0,
            "description": "Test webhook emit",
            "date": "2026-01-15",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    with app_fixture.app_context():
        events = (
            db.session.query(WebhookEvent).filter_by(event_type="expense.created").all()
        )
        assert len(events) >= 1


def test_bill_create_emits_event(client, auth_header, app_fixture):
    _create_subscription(client, auth_header, events=["bill.created"])

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": "2026-03-01",
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    with app_fixture.app_context():
        events = (
            db.session.query(WebhookEvent).filter_by(event_type="bill.created").all()
        )
        assert len(events) >= 1
