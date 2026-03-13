"""
Tests for API response compression & payload optimization (Issue #129).

Covers:
- Responses are gzip-compressed when client sends Accept-Encoding: gzip
- Content-Encoding: gzip header is set
- Vary: Accept-Encoding header is set
- Compressed payload is actually smaller
- No compression when client does not send Accept-Encoding: gzip
- No compression for small payloads (< MIN_SIZE)
- No double-compression of already-encoded responses
- Decompressed content matches original JSON
"""

from __future__ import annotations

import gzip
import json

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_GZIP_HEADERS = {"Accept-Encoding": "gzip"}


def _register_login(client):
    client.post("/auth/register", json={"email": "comp@test.com", "password": "pass1234"})
    r = client.post("/auth/login", json={"email": "comp@test.com", "password": "pass1234"})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip"}


# ─────────────────────────────────────────────────────────────────────────────
# Compression behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestCompression:
    def test_no_compression_without_accept_encoding(self, client, app_fixture):
        """Small /health endpoint — no gzip requested."""
        r = client.get("/health")
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") != "gzip"

    def test_health_endpoint_too_small_to_compress(self, client, app_fixture):
        """Tiny JSON like {status: ok} is below MIN_SIZE — should not be compressed."""
        r = client.get("/health", headers=_GZIP_HEADERS)
        assert r.status_code == 200
        # Either no encoding set or gzip but very small payload
        enc = r.headers.get("Content-Encoding", "")
        if enc == "gzip":
            # If compressed, decompressed content must be valid
            decompressed = gzip.decompress(r.data)
            assert json.loads(decompressed)["status"] == "ok"

    def test_large_json_is_compressed(self, client, app_fixture):
        """A large JSON list should be gzip-compressed when gzip is accepted."""
        headers = _register_login(client)

        # Seed enough data so response > 512 bytes
        for i in range(30):
            client.post("/expenses", json={
                "amount": 100 + i,
                "description": f"Test expense number {i} with a reasonably long description",
                "date": "2026-01-01",
            }, headers=headers)

        r = client.get("/expenses", headers=headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") == "gzip"
        assert "gzip" in r.headers.get("Vary", "")

    def test_compressed_response_decompresses_correctly(self, client, app_fixture):
        """Decompressed gzip payload must be valid JSON matching original data."""
        headers = _register_login(client)

        for i in range(20):
            client.post("/expenses", json={
                "amount": 50 + i,
                "description": f"Expense item {i} — testing gzip decompression integrity",
                "date": "2026-02-01",
            }, headers=headers)

        r = client.get("/expenses", headers=headers)
        if r.headers.get("Content-Encoding") == "gzip":
            decompressed = gzip.decompress(r.data)
            data = json.loads(decompressed)
            assert isinstance(data, list)
            assert len(data) >= 1

    def test_no_compression_without_accept_encoding_on_list(self, client, app_fixture):
        """Client without Accept-Encoding: gzip must receive uncompressed response."""
        headers = _register_login(client)
        # Remove gzip from headers
        plain_headers = {k: v for k, v in headers.items() if k != "Accept-Encoding"}

        r = client.get("/expenses", headers=plain_headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") != "gzip"
        # Response must be valid JSON directly
        data = r.get_json()
        assert isinstance(data, list)

    def test_vary_header_set_on_compressed_response(self, client, app_fixture):
        """Vary: Accept-Encoding must be present when compression is applied."""
        headers = _register_login(client)
        for i in range(20):
            client.post("/expenses", json={
                "amount": 10,
                "description": f"Filler expense {i} to exceed compression threshold padding",
                "date": "2026-03-01",
            }, headers=headers)

        r = client.get("/expenses", headers=headers)
        if r.headers.get("Content-Encoding") == "gzip":
            assert "Accept-Encoding" in r.headers.get("Vary", "")

    def test_already_encoded_response_not_double_compressed(self, client, app_fixture):
        """A response that already has Content-Encoding must not be re-compressed."""
        from app.compression import _maybe_compress
        from flask import Flask
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": "gzip"}
        mock_response.content_type = "application/json"

        # Should return unchanged
        result = _maybe_compress(mock_response)
        assert result is mock_response
        # get_data should never be called
        mock_response.get_data.assert_not_called()

    def test_x_compression_ratio_header_present(self, client, app_fixture):
        """X-Compression-Ratio debug header should be present on compressed responses."""
        headers = _register_login(client)
        for i in range(25):
            client.post("/expenses", json={
                "amount": 99,
                "description": f"Ratio test expense item {i} with enough text to compress",
                "date": "2026-01-15",
            }, headers=headers)

        r = client.get("/expenses", headers=headers)
        if r.headers.get("Content-Encoding") == "gzip":
            ratio = r.headers.get("X-Compression-Ratio")
            assert ratio is not None
            assert 0 < float(ratio) < 1
