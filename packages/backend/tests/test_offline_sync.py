def test_auth(client): assert client.get("/sync/status").status_code in (401, 422)
def test_push(client, auth_header):
    r = client.post("/sync/push", json={"changes": [{"type": "expense", "id": "1"}]}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["applied"] == 1
def test_pull(client, auth_header):
    r = client.get("/sync/pull", headers=auth_header)
    assert r.status_code == 200
def test_status(client, auth_header):
    r = client.get("/sync/status", headers=auth_header)
    assert r.status_code == 200
    assert "total_synced" in r.get_json()
