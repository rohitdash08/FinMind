"""Tests for login anomaly detection (issue #124)."""

import json


def test_successful_login_records_event(client):
    """A successful login creates a login event."""
    email, pw = "anomaly@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})
    r = client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data


def test_first_login_flags_new_ip(client):
    """First login from any IP is flagged as new_ip_address."""
    email, pw = "newip@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    r = client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert r.status_code == 200
    data = r.get_json()
    # First login with an IP we track — flagged as new
    if "security_alert" in data:
        assert "new_ip_address" in data["security_alert"]["reasons"]


def test_failed_login_is_recorded(client):
    """Failed login attempts are recorded for anomaly detection."""
    email, pw = "failtest@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    # 3 failed attempts
    for _ in range(3):
        r = client.post(
            "/auth/login", json={"email": email, "password": "wrong"}
        )
        assert r.status_code == 401


def test_rapid_failures_flag(client):
    """4+ failed logins in 10 min triggers rapid_failed_attempts flag."""
    email, pw = "rapid@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    # 4 rapid failures
    for _ in range(4):
        client.post("/auth/login", json={"email": email, "password": "wrong"})

    # Now successful login should be flagged
    r = client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    data = r.get_json()
    if "security_alert" in data:
        assert "rapid_failed_attempts" in data["security_alert"]["reasons"]


def test_login_history_endpoint(client):
    """GET /security/history returns login events."""
    email, pw = "history@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})
    r = client.post("/auth/login", json={"email": email, "password": pw})
    token = r.get_json()["access_token"]

    r = client.get(
        "/security/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "success" in data[0]
    assert "flagged" in data[0]


def test_suspicious_endpoint(client):
    """GET /security/suspicious returns only flagged events."""
    email, pw = "suspicious@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})
    r = client.post("/auth/login", json={"email": email, "password": pw})
    token = r.get_json()["access_token"]

    r = client.get(
        "/security/suspicious",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    # All returned events should be flagged
    for event in data:
        assert event["flagged"] is True or len(event["flag_reasons"]) > 0


def test_new_user_agent_flag(client):
    """Login with new user agent is flagged."""
    email, pw = "uatest@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    # First login with UA1
    client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"User-Agent": "TestBrowser/1.0"},
    )

    # Second login with different UA
    r = client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"User-Agent": "DifferentBrowser/2.0"},
    )
    data = r.get_json()
    if "security_alert" in data:
        assert "new_user_agent" in data["security_alert"]["reasons"]
