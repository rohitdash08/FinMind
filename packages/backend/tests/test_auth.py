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


def test_login_history_records_successful_login(client):
    email = "history@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindTest/1.0"},
        environ_base={"REMOTE_ADDR": "10.0.0.1"},
    )
    assert r.status_code == 200
    access = r.get_json()["access_token"]

    r = client.get("/auth/login-history", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    events = r.get_json()["events"]
    assert events[0]["success"] is True
    assert events[0]["ip_address"] == "10.0.0.1"
    assert events[0]["user_agent"] == "FinMindTest/1.0"


def test_new_ip_and_device_login_creates_alert(client):
    email = "alert@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "KnownDevice/1.0"},
        environ_base={"REMOTE_ADDR": "10.0.0.1"},
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "NewDevice/2.0"},
        environ_base={"REMOTE_ADDR": "10.0.0.2"},
    )
    assert r.status_code == 200
    access = r.get_json()["access_token"]

    r = client.get("/auth/login-history", headers={"Authorization": f"Bearer {access}"})
    latest = r.get_json()["events"][0]
    assert latest["is_suspicious"] is True
    assert "new_ip" in latest["suspicion_reasons"]
    assert "new_device" in latest["suspicion_reasons"]

    r = client.get("/auth/alerts", headers={"Authorization": f"Bearer {access}"})
    alerts = r.get_json()["alerts"]
    assert alerts[0]["alert_type"] == "suspicious_login"
    assert alerts[0]["acknowledged"] is False

    r = client.post(
        f"/auth/alerts/{alerts[0]['id']}/acknowledge",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    assert r.get_json()["acknowledged"] is True


def test_failed_login_burst_creates_alert_for_known_user(client):
    email = "burst@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    for _ in range(5):
        r = client.post("/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]

    r = client.get("/auth/alerts", headers={"Authorization": f"Bearer {access}"})
    messages = [alert["message"] for alert in r.get_json()["alerts"]]
    assert any("multiple failed login attempts" in message for message in messages)
