def test_backup_create_requires_auth(client):
    r = client.post("/backup/create")
    assert r.status_code == 401


def test_backup_create(client, auth_header):
    r = client.post("/backup/create", headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert "checksum" in data
    assert "size" in data
    assert data["size"] > 0


def test_backup_list(client, auth_header):
    # Create a backup first
    r = client.post("/backup/create", headers=auth_header)
    assert r.status_code == 201

    r = client.get("/backup/list", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "checksum" in data[0]
    assert "created_at" in data[0]
    assert "size" in data[0]


def test_backup_verify_valid(client, auth_header):
    # Create a backup
    r = client.post("/backup/create", headers=auth_header)
    assert r.status_code == 201
    checksum = r.get_json()["checksum"]

    # Verify it
    r = client.get(f"/backup/verify/{checksum}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["valid"] is True
    assert data["checksum"] == checksum


def test_backup_verify_not_found(client, auth_header):
    r = client.get("/backup/verify/nonexistent", headers=auth_header)
    assert r.status_code == 404


def test_backup_list_requires_auth(client):
    r = client.get("/backup/list")
    assert r.status_code == 401
