import hashlib
import hmac
from unittest.mock import patch, MagicMock


def _make_endpoint(client, auth_header, url="https://example.com/hook", events="*"):
    return client.post(
        "/webhooks",
        json={"url": url, "events": events},
        headers=auth_header,
    )


def test_create_webhook(client, auth_header):
    r = _make_endpoint(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["url"] == "https://example.com/hook"
    assert data["active"] is True
    assert "secret" in data  # shown once on creation
    assert len(data["secret"]) == 64  # 32 bytes hex


def test_create_webhook_requires_https(client, auth_header):
    r = _make_endpoint(client, auth_header, url="http://insecure.com/hook")
    assert r.status_code == 400


def test_list_webhooks(client, auth_header):
    _make_endpoint(client, auth_header, url="https://a.com/1")
    _make_endpoint(client, auth_header, url="https://b.com/2")
    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2


def test_update_webhook(client, auth_header):
    r = _make_endpoint(client, auth_header)
    ep_id = r.get_json()["id"]

    r = client.patch(
        f"/webhooks/{ep_id}",
        json={"url": "https://new-url.com/hook", "active": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["url"] == "https://new-url.com/hook"
    assert data["active"] is False


def test_delete_webhook(client, auth_header):
    r = _make_endpoint(client, auth_header)
    ep_id = r.get_json()["id"]

    r = client.delete(f"/webhooks/{ep_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/webhooks", headers=auth_header)
    assert len(r.get_json()) == 0


def test_webhook_isolation_between_users(client, auth_header):
    # create endpoint as user 1
    r = _make_endpoint(client, auth_header)
    ep_id = r.get_json()["id"]

    # register user 2
    client.post(
        "/auth/register", json={"email": "other@test.com", "password": "pass123"}
    )
    r = client.post(
        "/auth/login", json={"email": "other@test.com", "password": "pass123"}
    )
    other_token = r.get_json()["access_token"]
    other_header = {"Authorization": f"Bearer {other_token}"}

    # user 2 can't see user 1's endpoint
    r = client.get("/webhooks", headers=other_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 0

    # user 2 can't delete user 1's endpoint
    r = client.delete(f"/webhooks/{ep_id}", headers=other_header)
    assert r.status_code == 404


def test_test_endpoint(client, auth_header):
    r = _make_endpoint(client, auth_header)
    ep_id = r.get_json()["id"]

    with patch("app.routes.webhooks.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        r = client.post(f"/webhooks/{ep_id}/test", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["delivered"] is True

        # verify signature was sent
        call_args = mock_post.call_args
        headers = call_args[1]["headers"]
        assert "X-FinMind-Signature" in headers
        assert headers["X-FinMind-Event"] == "webhook.test"


def test_signature_verification():
    """verify our signature matches what a receiver would compute."""
    secret = "test-secret-key"
    payload = b'{"event":"test"}'
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    from app.routes.webhooks import _sign_payload

    assert _sign_payload(payload, secret) == expected


def test_event_filtering(client, auth_header):
    # endpoint only subscribes to expense.created and bill.paid
    r = _make_endpoint(client, auth_header, events="expense.created,bill.paid")
    ep_id = r.get_json()["id"]

    # verify via the API instead of querying model directly
    r = client.get("/webhooks", headers=auth_header)
    eps = r.get_json()
    ep = next(e for e in eps if e["id"] == ep_id)
    assert "expense.created" in ep["events"]
    assert "bill.paid" in ep["events"]
    assert "reminder.sent" not in ep["events"]
