def test_encryption_requires_auth(client):
    r = client.get("/encryption/keys")
    assert r.status_code in (401, 422)

    r = client.post("/encryption/keys", json={"key_id": "k1", "algorithm": "AES-256"})
    assert r.status_code in (401, 422)

    r = client.post("/encryption/verify", json={"data_hash": "a", "expected_hash": "a"})
    assert r.status_code in (401, 422)


def test_create_key_metadata(client, auth_header):
    r = client.post(
        "/encryption/keys",
        json={"key_id": "key-001", "algorithm": "AES-256"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["key_id"] == "key-001"
    assert data["algorithm"] == "AES-256"
    assert "created_at" in data


def test_list_key_metadata(client, auth_header):
    client.post(
        "/encryption/keys",
        json={"key_id": "key-a", "algorithm": "RSA-2048"},
        headers=auth_header,
    )
    client.post(
        "/encryption/keys",
        json={"key_id": "key-b", "algorithm": "AES-128"},
        headers=auth_header,
    )
    r = client.get("/encryption/keys", headers=auth_header)
    assert r.status_code == 200
    keys = r.get_json()
    assert len(keys) >= 2
    ids = [k["key_id"] for k in keys]
    assert "key-a" in ids
    assert "key-b" in ids


def test_verify_hash_match(client, auth_header):
    r = client.post(
        "/encryption/verify",
        json={"data_hash": "abc123", "expected_hash": "abc123"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["valid"] is True


def test_verify_hash_mismatch(client, auth_header):
    r = client.post(
        "/encryption/verify",
        json={"data_hash": "abc123", "expected_hash": "xyz789"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["valid"] is False
