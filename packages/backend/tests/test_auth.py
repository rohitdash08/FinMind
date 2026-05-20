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


def test_login_returns_non_suspicious_alert_for_first_success(client):
    email = "first-login@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindTest/1.0", "X-Forwarded-For": "203.0.113.10"},
    )
    assert r.status_code == 200
    alert = r.get_json()["security_alert"]
    assert alert == {"suspicious": False, "reason": None}


def test_login_flags_new_ip_address_after_successful_login(client):
    email = "new-ip@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindTest/1.0", "X-Forwarded-For": "203.0.113.10"},
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinMindTest/1.0", "X-Forwarded-For": "203.0.113.99"},
    )
    assert r.status_code == 200
    alert = r.get_json()["security_alert"]
    assert alert == {"suspicious": True, "reason": "new_ip_address"}


def test_login_flags_recent_failed_attempts(client):
    email = "failed-attempts@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    for _ in range(5):
        r = client.post("/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    alert = r.get_json()["security_alert"]
    assert alert == {"suspicious": True, "reason": "recent_failed_attempts"}


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
