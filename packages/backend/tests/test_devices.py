def test_device_trust_crud(client):
    # Register and login
    email = "devicetrust@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    # List devices (empty)
    r = client.get("/devices/", headers=auth)
    assert r.status_code == 200
    assert r.get_json() == []

    # Trust a device
    r = client.post(
        "/devices/",
        json={"device_name": "My Laptop"},
        headers=auth,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["device_name"] == "My Laptop"
    assert data["trusted"] is True
    device_id = data["id"]

    # List devices (1)
    r = client.get("/devices/", headers=auth)
    assert r.status_code == 200
    devices = r.get_json()
    assert len(devices) == 1
    assert devices[0]["device_name"] == "My Laptop"

    # Rename device
    r = client.patch(f"/devices/{device_id}", json={"device_name": "Work Laptop"}, headers=auth)
    assert r.status_code == 200
    assert r.get_json()["device_name"] == "Work Laptop"

    # Revoke device
    r = client.delete(f"/devices/{device_id}", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["trusted"] is False

    # Verify it shows as untrusted
    r = client.get("/devices/", headers=auth)
    devices = r.get_json()
    assert len(devices) == 1
    assert devices[0]["trusted"] is False


def test_device_trust_requires_name(client):
    email = "noname@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.post("/devices/", json={"device_name": ""}, headers=auth)
    assert r.status_code == 400


def test_device_re_trust(client):
    email = "retrust@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    # Trust
    r = client.post("/devices/", json={"device_name": "Phone"}, headers=auth)
    assert r.status_code == 201
    device_id = r.get_json()["id"]

    # Revoke
    client.delete(f"/devices/{device_id}", headers=auth)

    # Re-trust same device (same UA/IP = same fingerprint) -> updates existing
    r = client.post("/devices/", json={"device_name": "Phone"}, headers=auth)
    assert r.status_code == 200
    assert r.get_json()["trusted"] is True
    assert r.get_json()["id"] == device_id


def test_device_revoke_not_found(client):
    email = "nofound@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.delete("/devices/9999", headers=auth)
    assert r.status_code == 404
