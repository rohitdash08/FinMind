def test_cache_stats_requires_auth(client):
    r = client.get("/cache/stats")
    assert r.status_code == 401


def test_cache_stats(client, auth_header):
    r = client.get("/cache/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "total_keys" in data
    assert "hits" in data
    assert "misses" in data
    assert "hit_rate" in data


def test_cache_invalidate_requires_auth(client):
    r = client.post("/cache/invalidate")
    assert r.status_code == 401


def test_cache_invalidate_all(client, auth_header):
    r = client.post("/cache/invalidate", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "deleted" in data


def test_cache_invalidate_specific_keys(client, auth_header):
    r = client.post(
        "/cache/invalidate",
        json={"keys": ["dashboard_summary", "insights"]},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "deleted" in data


def test_cache_keys_requires_auth(client):
    r = client.get("/cache/keys")
    assert r.status_code == 401


def test_cache_keys_list(client, auth_header):
    r = client.get("/cache/keys", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "keys" in data
    assert isinstance(data["keys"], list)
