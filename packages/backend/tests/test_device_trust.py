def test_list_devices_requires_auth(client):
    r = client.get("/devices")
    assert r.status_code == 401


def test_trust_device(client, auth_header):
    r = client.post("/devices/trust", headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert "id" in data
    assert "fingerprint" in data


def test_list_devices(client, auth_header):
    # Trust a device first
    r = client.post("/devices/trust", headers=auth_header)
    assert r.status_code == 201

    r = client.get("/devices", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "id" in data[0]
    assert "trusted_at" in data[0]


def test_revoke_device(client, auth_header):
    # Trust a device first
    r = client.post("/devices/trust", headers=auth_header)
    assert r.status_code == 201
    device_id = r.get_json()["id"]

    # Revoke it
    r = client.delete(f"/devices/{device_id}/revoke", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "device revoked"

    # Should no longer appear in list
    r = client.get("/devices", headers=auth_header)
    assert r.status_code == 200
    ids = [d["id"] for d in r.get_json()]
    assert device_id not in ids


def test_revoke_nonexistent_device(client, auth_header):
    r = client.delete("/devices/99999/revoke", headers=auth_header)
    assert r.status_code == 404
