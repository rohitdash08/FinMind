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

def test_device_trust_management_flow(client):
    email = "devices@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password, "device_id": "laptop-1", "device_name": "Work Laptop"},
        headers={"User-Agent": "FinMindTest/1.0", "X-Forwarded-For": "203.0.113.10"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    access = payload["access_token"]
    device = payload["device"]
    assert device["device_id"] == "laptop-1"
    assert device["name"] == "Work Laptop"
    assert device["trusted"] is False
    assert device["last_ip"] == "203.0.113.10"
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/devices", headers=auth)
    assert r.status_code == 200
    devices = r.get_json()["devices"]
    assert len(devices) == 1
    device_pk = devices[0]["id"]

    r = client.patch(
        f"/auth/devices/{device_pk}",
        json={"trusted": True, "name": "Primary Laptop"},
        headers=auth,
    )
    assert r.status_code == 200
    updated = r.get_json()["device"]
    assert updated["trusted"] is True
    assert updated["name"] == "Primary Laptop"

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password, "device_id": "laptop-1"},
    )
    assert r.status_code == 200
    assert r.get_json()["device"]["trusted"] is True

    r = client.delete(f"/auth/devices/{device_pk}", headers=auth)
    assert r.status_code == 200
    revoked = r.get_json()["device"]
    assert revoked["trusted"] is False
    assert revoked["revoked_at"] is not None

    r = client.patch(
        f"/auth/devices/{device_pk}",
        json={"trusted": True},
        headers=auth,
    )
    assert r.status_code == 409


def test_device_listing_is_user_scoped(client):
    for email, device_id in [("owner@test.com", "owner-phone"), ("other@test.com", "other-phone")]:
        r = client.post("/auth/register", json={"email": email, "password": "secret123"})
        assert r.status_code in (201, 409)
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "secret123", "device_id": device_id},
        )
        assert r.status_code == 200
        if email == "owner@test.com":
            owner_access = r.get_json()["access_token"]

    r = client.get("/auth/devices", headers={"Authorization": f"Bearer {owner_access}"})
    assert r.status_code == 200
    devices = r.get_json()["devices"]
    assert [device["device_id"] for device in devices] == ["owner-phone"]

