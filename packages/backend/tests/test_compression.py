def test_compression_gzip_small_payload_not_compressed(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "Content-Encoding" not in r.headers or r.headers.get("Content-Encoding") == "identity"
    assert r.get_json()["status"] == "ok"


def test_compression_gzip_large_response(client, auth_header):
    for i in range(50):
        client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"Test expense {i}",
                "date": "2026-02-01",
            },
            headers=auth_header,
        )
    r = client.get(
        "/expenses?page_size=50",
        headers={**auth_header, "Accept-Encoding": "gzip"},
    )
    assert r.status_code == 200
    assert r.headers.get("Content-Encoding") == "gzip"


def test_compression_brotli_when_accepted(client, auth_header):
    for i in range(50):
        client.post(
            "/expenses",
            json={
                "amount": 5.0 + i,
                "description": f"Brotli test {i}",
                "date": "2026-03-01",
            },
            headers=auth_header,
        )
    r = client.get(
        "/expenses?page_size=50",
        headers={**auth_header, "Accept-Encoding": "br"},
    )
    assert r.status_code == 200
    assert r.headers.get("Content-Encoding") == "br"


def test_compression_data_integrity(client, auth_header):
    payload = {
        "amount": 42.0,
        "description": "Integrity check expense",
        "date": "2026-04-15",
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201

    r = client.get(
        "/expenses?search=Integrity+check",
        headers={**auth_header, "Accept-Encoding": "gzip"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "data" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["description"] == "Integrity check expense"
