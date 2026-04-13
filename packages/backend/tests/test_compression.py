def test_auth(client): assert client.get("/compression/stats").status_code in (401, 422)
def test_stats(client, auth_header):
    r = client.get("/compression/stats", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["compression_enabled"] is True
def test_optimize(client, auth_header):
    big = {"items": [{"id": i, "name": f"item_{i}", "value": i*100} for i in range(50)]}
    r = client.post("/compression/optimize", json={"payload": big}, headers=auth_header)
    assert r.status_code == 200
    d = r.get_json()
    assert d["compressed_size"] < d["original_size"]
    assert d["savings_pct"] > 0
def test_config(client, auth_header):
    r = client.get("/compression/config", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["gzip_enabled"] is True
def test_optimize_missing(client, auth_header):
    r = client.post("/compression/optimize", json={}, headers=auth_header)
    assert r.status_code == 400
