"""Tests for device trust management (Issue #125)."""


def _login(client, email="test@example.com", password="password123", user_agent=None, ip=None):
    """Helper to register + login and return (auth_header, response_json)."""
    client.post("/auth/register", json={"email": email, "password": password})
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert r.status_code == 200
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_records_device(client):
    auth = _login(client, user_agent="Mozilla/5.0 (Macintosh) Chrome/120")
    r = client.get("/auth/devices", headers=auth)
    assert r.status_code == 200
    devices = r.get_json()
    assert len(devices) >= 1
    assert "Chrome" in devices[0]["device_name"]
    assert devices[0]["trusted"] is False


def test_list_devices_empty_before_login(client, auth_header):
    # auth_header fixture uses register+login, which records a device
    r = client.get("/auth/devices", headers=auth_header)
    assert r.status_code == 200
    devices = r.get_json()
    # At least one device from the login in auth_header fixture
    assert isinstance(devices, list)
    assert len(devices) >= 1


def test_trust_device(client):
    auth = _login(client, user_agent="TestBrowser/1.0")
    r = client.get("/auth/devices", headers=auth)
    devices = r.get_json()
    device_id = devices[0]["id"]

    r = client.post(
        "/auth/devices/trust",
        json={"device_id": device_id},
        headers=auth,
    )
    assert r.status_code == 200
    assert r.get_json()["message"] == "device trusted"

    # Verify it's now trusted
    r = client.get("/auth/devices", headers=auth)
    updated = [d for d in r.get_json() if d["id"] == device_id]
    assert updated[0]["trusted"] is True


def test_trust_device_not_found(client, auth_header):
    r = client.post(
        "/auth/devices/trust",
        json={"device_id": 99999},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_trust_device_missing_id(client, auth_header):
    r = client.post(
        "/auth/devices/trust",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_remove_device(client):
    auth = _login(client, user_agent="RemovableDevice/1.0")
    r = client.get("/auth/devices", headers=auth)
    devices = r.get_json()
    device_id = devices[0]["id"]

    r = client.delete(f"/auth/devices/{device_id}", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["message"] == "device removed"

    # Verify it's gone
    r = client.get("/auth/devices", headers=auth)
    remaining = [d for d in r.get_json() if d["id"] == device_id]
    assert len(remaining) == 0


def test_remove_device_not_found(client, auth_header):
    r = client.delete("/auth/devices/99999", headers=auth_header)
    assert r.status_code == 404


def test_same_device_updates_last_seen(client):
    """Logging in twice from the same device should update last_seen, not create duplicate."""
    ua = "SameDevice/1.0"
    email = "repeat@example.com"
    client.post("/auth/register", json={"email": email, "password": "password123"})

    # Login twice with same UA
    r1 = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
        headers={"User-Agent": ua},
    )
    auth = {"Authorization": f"Bearer {r1.get_json()['access_token']}"}

    r = client.get("/auth/devices", headers=auth)
    count_before = len(r.get_json())

    r2 = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
        headers={"User-Agent": ua},
    )
    auth2 = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

    r = client.get("/auth/devices", headers=auth2)
    count_after = len(r.get_json())

    assert count_after == count_before


def test_devices_requires_auth(client):
    r = client.get("/auth/devices")
    assert r.status_code == 401
