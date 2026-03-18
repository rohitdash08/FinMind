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


def test_login_brute_force_prevention(client):
    email = "brute@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Login once successfully to get token to verify alerts later
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access_token = r.get_json()["access_token"]
    auth_header = {"Authorization": f"Bearer {access_token}"}

    # 5 Failed attempts
    for _ in range(5):
        r = client.post(
            "/auth/login", json={"email": email, "password": "wrongpassword"}
        )
        if r.status_code == 429:
            break
        assert r.status_code == 401

    # the 6th attempt should definitely be 429
    r = client.post("/auth/login", json={"email": email, "password": "wrongpassword"})
    assert r.status_code == 429

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 429  # Even with correct password, they are locked out

    # Check that a BRUTE_FORCE alert was created
    r = client.get("/auth/alerts", headers=auth_header)
    assert r.status_code == 200
    alerts = r.get_json()["alerts"]
    brute_force_alerts = [a for a in alerts if a["alert_type"] == "BRUTE_FORCE"]
    assert len(brute_force_alerts) >= 1


def test_login_security_alerts_new_device(client):
    email = "alerts@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    headers_ip1 = {"X-Forwarded-For": "192.168.1.100"}

    # First successful login from IP1
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers=headers_ip1,
    )
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    # Fetch alerts for IP1
    r = client.get("/auth/alerts", headers=auth)
    assert r.status_code == 200
    alerts = r.get_json()["alerts"]
    new_device_alerts = [a for a in alerts if a["alert_type"] == "NEW_DEVICE_LOGIN"]
    assert len(new_device_alerts) == 1

    new_device_alert_id = new_device_alerts[0]["id"]

    # Mark read
    r = client.patch(f"/auth/alerts/{new_device_alert_id}/read", headers=auth)
    assert r.status_code == 200

    r = client.get("/auth/alerts", headers=auth)
    assert r.status_code == 200
    alerts = r.get_json()["alerts"]
    for a in alerts:
        if a["id"] == new_device_alert_id:
            assert a["is_read"] is True

    # Login again from same IP1 - should not generate a new alert
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers=headers_ip1,
    )
    assert r.status_code == 200

    r = client.get("/auth/alerts", headers=auth)
    alerts = r.get_json()["alerts"]
    new_device_alerts = [a for a in alerts if a["alert_type"] == "NEW_DEVICE_LOGIN"]
    assert len(new_device_alerts) == 1  # Still 1 alert

    # Login from new IP2 - should trigger new device alert
    headers_ip2 = {"X-Forwarded-For": "10.0.0.5"}
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers=headers_ip2,
    )
    assert r.status_code == 200

    r = client.get("/auth/alerts", headers=auth)
    alerts = r.get_json()["alerts"]
    new_device_alerts = [a for a in alerts if a["alert_type"] == "NEW_DEVICE_LOGIN"]
    assert len(new_device_alerts) == 2  # Now 2 alerts
