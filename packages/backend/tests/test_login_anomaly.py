"""Tests for login anomaly detection and suspicious activity alerts."""

import json


def _register_and_login(client, email="anomaly@test.com", password="secret123"):
    """Helper: register user and login, return (access_token, refresh_token)."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    return data["access_token"], data.get("refresh_token")


# ------------------------------------------------------------------
# Login event recording
# ------------------------------------------------------------------

def test_login_records_event(client):
    """Successful login should persist a LoginEvent row."""
    access, _ = _register_and_login(client)
    auth = {"Authorization": f"Bearer {access}"}
    r = client.get("/auth/login-history", headers=auth)
    assert r.status_code == 200
    events = r.get_json()
    assert isinstance(events, list)
    # At least 1 login event (the one we just did)
    assert len(events) >= 1
    assert events[0]["success"] is True


def test_failed_login_records_event(client):
    """Failed login should record an event with success=False."""
    email = "failtrack@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    # fail
    client.post("/auth/login", json={"email": email, "password": "wrong"})
    # succeed to get token
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}
    r = client.get("/auth/login-history", headers=auth)
    events = r.get_json()
    successes = [e for e in events if e["success"]]
    failures = [e for e in events if not e["success"]]
    assert len(failures) >= 1
    assert len(successes) >= 1


# ------------------------------------------------------------------
# Anomaly detection — new IP triggers warning
# ------------------------------------------------------------------

def test_new_ip_triggers_warning(client, app_fixture):
    """Login from a new IP should include security_warnings in response."""
    email = "newip@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login — establishes baseline
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert r.status_code == 200

    # Second login from different IP
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "99.99.99.99"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "security_warnings" in data
    assert any("New IP" in w for w in data["security_warnings"])


# ------------------------------------------------------------------
# Alerts endpoint
# ------------------------------------------------------------------

def test_alerts_endpoint(client, app_fixture):
    """Security alerts should be retrievable via GET /auth/alerts."""
    email = "alerts@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # login from IP A
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    # login from IP B (should trigger alert)
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/alerts", headers=auth)
    assert r.status_code == 200
    alerts = r.get_json()
    assert isinstance(alerts, list)
    assert len(alerts) >= 1
    assert alerts[0]["alert_type"] == "NEW_IP"


def test_acknowledge_alert(client, app_fixture):
    """POST /auth/alerts/<id>/acknowledge should mark alert as acknowledged."""
    email = "ack@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/alerts", headers=auth)
    alerts = r.get_json()
    assert len(alerts) >= 1
    alert_id = alerts[0]["id"]

    r = client.post(f"/auth/alerts/{alert_id}/acknowledge", headers=auth)
    assert r.status_code == 200

    # Verify it's acknowledged
    r = client.get("/auth/alerts?unacknowledged=true", headers=auth)
    remaining = [a for a in r.get_json() if a["id"] == alert_id]
    assert len(remaining) == 0


def test_acknowledge_nonexistent_alert(client):
    """Acknowledging a non-existent alert returns 404."""
    access, _ = _register_and_login(client, email="nonexist@test.com")
    auth = {"Authorization": f"Bearer {access}"}
    r = client.post("/auth/alerts/99999/acknowledge", headers=auth)
    assert r.status_code == 404


# ------------------------------------------------------------------
# Anomaly service unit-level
# ------------------------------------------------------------------

def test_anomaly_score_zero_on_first_login(client, app_fixture):
    """The very first login should have score 0 (no history to compare)."""
    email = "first@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    # No warnings on first ever login
    assert "security_warnings" not in data or len(data.get("security_warnings", [])) == 0

    access = data["access_token"]
    auth = {"Authorization": f"Bearer {access}"}
    r = client.get("/auth/login-history", headers=auth)
    events = r.get_json()
    assert events[0]["anomaly_score"] == 0.0
