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


def test_login_anomaly_alert_created_for_new_network(client):
    email = "anomaly@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    first = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindTest/1.0"},
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
    )
    assert first.status_code == 200
    first_data = first.get_json()
    assert first_data["security_alert"]["suspicious"] is False

    second = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindTest/1.0"},
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
    )
    assert second.status_code == 200
    assert second.get_json()["security_alert"]["suspicious"] is False

    suspicious = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={
            "User-Agent": "FinMindTest/1.0",
            "X-Forwarded-For": "198.51.100.20",
        },
    )
    assert suspicious.status_code == 200
    suspicious_data = suspicious.get_json()
    assert suspicious_data["security_alert"]["suspicious"] is True
    assert suspicious_data["security_alert"]["reasons"] == ["new_ip"]

    access = suspicious_data["access_token"]
    auth = {"Authorization": f"Bearer {access}"}
    alerts = client.get("/auth/security-alerts", headers=auth)
    assert alerts.status_code == 200
    alerts_data = alerts.get_json()
    assert len(alerts_data) == 1
    assert alerts_data[0]["type"] == "login_anomaly"
    assert alerts_data[0]["read"] is False
    assert alerts_data[0]["details"]["ip"] == "198.51.100.x"

    unread = client.get("/auth/security-alerts?unread_only=true", headers=auth)
    assert unread.status_code == 200
    assert len(unread.get_json()) == 1

    alert_id = alerts_data[0]["id"]
    marked = client.patch(f"/auth/security-alerts/{alert_id}/read", headers=auth)
    assert marked.status_code == 200
    assert marked.get_json()["read"] is True

    unread = client.get("/auth/security-alerts?unread_only=true", headers=auth)
    assert unread.status_code == 200
    assert unread.get_json() == []
