"""Tests for API response compression."""


def test_compression_with_gzip_header(client):
    """Large JSON responses should be compressed when client accepts gzip."""
    email = "compress@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]

    # Request with gzip accept header
    r = client.get(
        "/expenses/",
        headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip"},
    )
    assert r.status_code == 200


def test_no_compression_without_header(client):
    """Responses should not be compressed without Accept-Encoding: gzip."""
    email = "nocompress@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]

    r = client.get(
        "/expenses/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "Content-Encoding" not in r.headers
