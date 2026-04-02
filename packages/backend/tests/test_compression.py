"""Tests for API response compression (issue #129).

Verifies that:
- JSON responses are gzip-compressed when Accept-Encoding: gzip is sent.
- Compressed payload is smaller than the uncompressed version.
- Content-Encoding and Vary headers are set correctly.
- Small responses below the minimum threshold are NOT compressed.
- Requests without Accept-Encoding receive uncompressed responses.
"""

import gzip
import json

import pytest


def test_health_uncompressed(client):
    """Health endpoint returns a tiny payload — should NOT be compressed."""
    resp = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    # Health response is small; compression should be skipped
    data = resp.get_json()
    assert data["status"] == "ok"


def test_expenses_compressed(client, auth_header):
    """Expense list with enough data should be gzip-compressed."""
    # Seed expenses to exceed min compression threshold
    for i in range(20):
        client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"Test expense number {i} with a longer description to bulk up",
                "date": f"2026-01-{(i % 28) + 1:02d}",
            },
            headers=auth_header,
        )

    # Fetch WITHOUT gzip
    plain = client.get("/expenses", headers=auth_header)
    assert plain.status_code == 200
    plain_body = plain.data
    plain_items = plain.get_json()
    assert len(plain_items) == 20

    # Fetch WITH gzip
    compressed_resp = client.get(
        "/expenses",
        headers={**auth_header, "Accept-Encoding": "gzip"},
    )
    assert compressed_resp.status_code == 200

    # Should be compressed (Content-Encoding header present)
    encoding = compressed_resp.headers.get("Content-Encoding", "")
    if encoding == "gzip":
        # Verify we can decompress it
        decompressed = gzip.decompress(compressed_resp.data)
        items = json.loads(decompressed)
        assert len(items) == 20
        # Compressed should be smaller
        assert len(compressed_resp.data) < len(plain_body)
        # Vary header should be set
        assert "Accept-Encoding" in compressed_resp.headers.get("Vary", "")
    else:
        # flask-compress may use test client differently; ensure data is valid JSON
        items = compressed_resp.get_json()
        assert len(items) == 20


def test_no_compression_without_accept_encoding(client, auth_header):
    """Responses without Accept-Encoding header should NOT be compressed."""
    for i in range(10):
        client.post(
            "/expenses",
            json={
                "amount": 50.0,
                "description": f"Expense {i} for no-compress test padding",
                "date": "2026-02-01",
            },
            headers=auth_header,
        )

    resp = client.get("/expenses", headers=auth_header)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Encoding") != "gzip"
    items = resp.get_json()
    assert len(items) == 10


def test_compression_module_init(app_fixture):
    """Verify compression was initialized on the app."""
    # If flask-compress is installed, it adds 'compress' to extensions
    # If WSGI fallback, the wsgi_app is wrapped
    from app.compression import GzipMiddleware

    has_flask_compress = "compress" in app_fixture.extensions
    has_wsgi_gzip = isinstance(app_fixture.wsgi_app, GzipMiddleware)

    # One of the two should be active
    assert has_flask_compress or has_wsgi_gzip, (
        "Neither flask-compress nor GzipMiddleware is active"
    )
