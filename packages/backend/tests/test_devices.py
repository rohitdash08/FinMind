def test_get_current_device(client, auth_header):
    """GET /devices/current should create and return device info."""
    r = client.get("/devices/current", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "id" in data
    assert "device_fingerprint" in data
    assert "device_name" in data
    assert data["is_trusted"] is False


def test_list_devices_empty(client, auth_header):
    """GET /devices/ should return empty list when no devices recorded."""
    r = client.get("/devices/", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_devices_after_current(client, auth_header):
    """After visiting /current, the device should appear in the list."""
    client.get("/devices/current", headers=auth_header)
    r = client.get("/devices/", headers=auth_header)
    assert r.status_code == 200
    devices = r.get_json()
    assert len(devices) >= 1


def test_trust_device(client, auth_header):
    """POST /devices/trust should mark device as trusted."""
    r = client.get("/devices/current", headers=auth_header)
    device_id = r.get_json()["id"]

    r = client.post(
        "/devices/trust",
        json={"device_id": device_id},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["is_trusted"] is True


def test_trust_device_missing_id(client, auth_header):
    """POST /devices/trust without device_id should return 400."""
    r = client.post("/devices/trust", json={}, headers=auth_header)
    assert r.status_code == 400


def test_trust_device_not_found(client, auth_header):
    """POST /devices/trust with non-existent ID should return 404."""
    r = client.post(
        "/devices/trust",
        json={"device_id": 99999},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_remove_device(client, auth_header):
    """DELETE /devices/<id> should remove the device."""
    r = client.get("/devices/current", headers=auth_header)
    device_id = r.get_json()["id"]

    r = client.delete(f"/devices/{device_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "device removed"

    # Verify it's gone
    r = client.get("/devices/", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 0


def test_remove_device_not_found(client, auth_header):
    """DELETE /devices/<id> with non-existent ID should return 404."""
    r = client.delete("/devices/99999", headers=auth_header)
    assert r.status_code == 404


def test_current_device_idempotent(client, auth_header):
    """Calling /devices/current twice should return the same device."""
    r1 = client.get("/devices/current", headers=auth_header)
    r2 = client.get("/devices/current", headers=auth_header)
    assert r1.get_json()["id"] == r2.get_json()["id"]


def test_devices_requires_auth(client):
    """All device endpoints should require authentication."""
    assert client.get("/devices/").status_code == 401
    assert client.get("/devices/current").status_code == 401
    assert client.post("/devices/trust", json={}).status_code == 401
    assert client.delete("/devices/1").status_code == 401
