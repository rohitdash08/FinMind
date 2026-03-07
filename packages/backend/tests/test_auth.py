def test_auth_refresh_flow(client):
    # Register user
    email = "refresh@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)  # 409 if already exists

    # Login to get tokens
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data and "refresh_token" in data

    # Use refresh to get a new access token
    refresh_token = data["refresh_token"]
    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200
    new_access = r.get_json().get("access_token")
    assert isinstance(new_access, str) and len(new_access) > 10


def test_auth_logout_revokes_refresh_token(client):
    email = "logout@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    refresh_token = r.get_json()["refresh_token"]

    r = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 401


def test_auth_me_and_update_preferred_currency(client):
    email = "profile@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    me = r.get_json()
    assert me["email"] == email
    assert me["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "inr"}, headers=auth)
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "ZZZ"}, headers=auth)
    assert r.status_code == 400


def test_login_flags_new_ip_as_suspicious_and_lists_alerts(client):
    email = "security-ip@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    # Baseline login from known IP should not trigger an alert.
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindBrowser/1.0"},
        environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
    )
    assert r.status_code == 200
    first_login = r.get_json()
    assert first_login["suspicious_activity_alert"]["triggered"] is False

    # Login from a new IP should trigger suspicious activity alert.
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindBrowser/1.0"},
        environ_overrides={"REMOTE_ADDR": "10.0.0.99"},
    )
    assert r.status_code == 200
    second_login = r.get_json()
    assert second_login["suspicious_activity_alert"]["triggered"] is True
    assert "NEW_IP_ADDRESS" in second_login["suspicious_activity_alert"]["reasons"]

    access = second_login["access_token"]
    auth = {"Authorization": f"Bearer {access}"}
    r = client.get("/auth/security-alerts", headers=auth)
    assert r.status_code == 200
    alerts = r.get_json()
    assert len(alerts) == 1
    assert alerts[0]["reason_codes"] == ["NEW_IP_ADDRESS"]
    assert alerts[0]["ip_address"] == "10.0.0.99"


def test_login_flags_multiple_recent_failed_attempts(client):
    email = "security-failed@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    for _ in range(5):
        failed = client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-password"},
            headers={"User-Agent": "FinMindBrowser/1.0"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.5"},
        )
        assert failed.status_code == 401

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindBrowser/1.0"},
        environ_overrides={"REMOTE_ADDR": "10.0.0.5"},
    )
    assert r.status_code == 200
    login = r.get_json()
    assert login["suspicious_activity_alert"]["triggered"] is True
    assert "MULTIPLE_FAILED_ATTEMPTS" in login["suspicious_activity_alert"]["reasons"]
