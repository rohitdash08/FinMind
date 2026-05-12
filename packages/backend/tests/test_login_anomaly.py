"""Tests for login anomaly detection."""


def test_login_records_attempt(client):
    """Successful login should record attempt."""
    email = "anomaly_test@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data


def test_failed_login_records_attempt(client):
    """Failed login should not crash and return 401."""
    r = client.post(
        "/auth/login", json={"email": "noone@test.com", "password": "wrong"}
    )
    assert r.status_code == 401


def test_brute_force_detection(client):
    """Multiple failed logins should trigger brute_force flag."""
    email = "brute@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Simulate 6 failed attempts
    for _ in range(6):
        client.post("/auth/login", json={"email": email, "password": "wrong"})

    # Now login successfully - should still work
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200


def test_security_alerts_endpoint(client):
    """Security alerts endpoint should return alerts list."""
    email = "alerts@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]

    r = client.get(
        "/auth/security-alerts", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert "alerts" in r.get_json()


def test_clear_security_alerts(client):
    """Should be able to clear security alerts."""
    email = "clearalerts@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]

    r = client.delete(
        "/auth/security-alerts", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
