"""Tests for webhook event system."""

def test_webhooks_requires_auth(client):
    assert client.get("/webhooks").status_code in (401, 422)

def test_create_subscription(client, auth_header):
    r = client.post("/webhooks", json={"url": "https://example.com/hook", "events": ["expense.created"]}, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["url"] == "https://example.com/hook"
    assert "expense.created" in data["events"]

def test_list_subscriptions(client, auth_header):
    client.post("/webhooks", json={"url": "https://a.com", "events": ["expense.created"]}, headers=auth_header)
    r = client.get("/webhooks", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 1

def test_delete_subscription(client, auth_header):
    r = client.post("/webhooks", json={"url": "https://del.com", "events": ["bill.due"]}, headers=auth_header)
    sub_id = r.get_json()["id"]
    r = client.delete(f"/webhooks/{sub_id}", headers=auth_header)
    assert r.status_code == 200

def test_invalid_event(client, auth_header):
    r = client.post("/webhooks", json={"url": "https://x.com", "events": ["invalid.event"]}, headers=auth_header)
    assert r.status_code == 400

def test_missing_url(client, auth_header):
    r = client.post("/webhooks", json={"url": "", "events": ["expense.created"]}, headers=auth_header)
    assert r.status_code == 400

def test_list_valid_events(client, auth_header):
    r = client.get("/webhooks/events", headers=auth_header)
    assert r.status_code == 200
    events = r.get_json()["events"]
    assert "expense.created" in events
    assert "bill.due" in events

def test_test_webhook_not_found(client, auth_header):
    r = client.post("/webhooks/test", json={"subscription_id": 9999}, headers=auth_header)
    assert r.status_code == 404
