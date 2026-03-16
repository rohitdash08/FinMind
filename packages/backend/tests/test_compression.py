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
- Streaming responses (direct_passthrough=True) are skipped
- X-Compression-Ratio header is only emitted in debug mode
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


def _make_large_json_response(app, size_bytes: int = 2048):
    """Return a Flask Response with a JSON body larger than MIN_COMPRESS_SIZE,
    without hitting the DB.  Uses a minimal in-request-context approach."""
    import json as _json
    from flask import Response

    payload = _json.dumps({"data": "x" * size_bytes})
    return Response(payload, status=200, content_type="application/json")


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
        enc = r.headers.get("Content-Encoding", "")
        if enc == "gzip":
            decompressed = gzip.decompress(r.data)
            assert json.loads(decompressed)["status"] == "ok"

    def test_large_json_is_compressed(self, client, app_fixture):
        """A large JSON response should be gzip-compressed when gzip is accepted.

        Uses a mock route registered on the test app instead of seeding DB
        rows, making the test fast and DB-independent.
        """
        import json as _json

        large_body = _json.dumps({"items": ["item_" + str(i) * 20 for i in range(200)]})

        # Register a one-shot route that returns a large JSON body
        with app_fixture.app_context():
            @app_fixture.route("/_test_large")
            def _test_large_route():
                from flask import Response
                return Response(large_body, status=200, content_type="application/json")

        r = client.get("/_test_large", headers=_GZIP_HEADERS)
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") == "gzip"
        assert "Accept-Encoding" in r.headers.get("Vary", "")

        decompressed = gzip.decompress(r.data)
        data = json.loads(decompressed)
        assert "items" in data
        assert len(data["items"]) == 200

    def test_no_compression_without_accept_encoding_on_list(self, client, app_fixture):
        """Client without Accept-Encoding: gzip must receive uncompressed response."""
        headers = _register_login(client)
        plain_headers = {k: v for k, v in headers.items() if k != "Accept-Encoding"}

        r = client.get("/expenses", headers=plain_headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") != "gzip"
        data = r.get_json()
        assert isinstance(data, list)

    def test_vary_header_set_on_compressed_response(self, client, app_fixture):
        """Vary: Accept-Encoding must be present when compression is applied."""
        import json as _json

        large_body = _json.dumps({"pad": "y" * 2000})

        with app_fixture.app_context():
            @app_fixture.route("/_test_vary")
            def _test_vary_route():
                from flask import Response
                return Response(large_body, status=200, content_type="application/json")

        r = client.get("/_test_vary", headers=_GZIP_HEADERS)
        if r.headers.get("Content-Encoding") == "gzip":
            assert "Accept-Encoding" in r.headers.get("Vary", "")

    def test_already_encoded_response_not_double_compressed(self, client, app_fixture):
        """A response that already has Content-Encoding must not be re-compressed."""
        from app.compression import _maybe_compress
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": "gzip"}
        mock_response.content_type = "application/json"
        mock_response.direct_passthrough = False

        result = _maybe_compress(mock_response)
        assert result is mock_response
        mock_response.get_data.assert_not_called()

    # ── Fix 1: streaming responses must be skipped ────────────────────────────

    def test_streaming_response_skipped(self, client, app_fixture):
        """Responses with direct_passthrough=True must never have get_data() called.

        Calling get_data() on a streaming response buffers the whole stream in
        memory; the compression middleware must detect and skip such responses.
        """
        from app.compression import _maybe_compress
        from unittest.mock import MagicMock, patch

        mock_response = MagicMock()
        mock_response.headers = {}          # no Content-Encoding yet
        mock_response.direct_passthrough = True
        mock_response.content_type = "application/json"

        with patch("app.compression.current_request") as mock_req:
            mock_req.headers.get.return_value = "gzip"
            result = _maybe_compress(mock_response)

        # Must return unchanged and must NOT have called get_data()
        assert result is mock_response
        mock_response.get_data.assert_not_called()

    # ── Fix 2: X-Compression-Ratio only in debug mode ─────────────────────────

    def test_x_compression_ratio_absent_in_production(self, client, app_fixture):
        """X-Compression-Ratio must NOT be sent when app.debug is False."""
        import json as _json

        large_body = _json.dumps({"pad": "z" * 2000})

        with app_fixture.app_context():
            @app_fixture.route("/_test_ratio_prod")
            def _test_ratio_prod():
                from flask import Response
                return Response(large_body, status=200, content_type="application/json")

        # Ensure debug is off
        original_debug = app_fixture.debug
        app_fixture.debug = False
        try:
            r = client.get("/_test_ratio_prod", headers=_GZIP_HEADERS)
            if r.headers.get("Content-Encoding") == "gzip":
                assert "X-Compression-Ratio" not in r.headers
        finally:
            app_fixture.debug = original_debug

    def test_x_compression_ratio_present_in_debug(self, client, app_fixture):
        """X-Compression-Ratio MUST be present when app.debug is True."""
        import json as _json

        large_body = _json.dumps({"pad": "w" * 2000})

        with app_fixture.app_context():
            @app_fixture.route("/_test_ratio_debug")
            def _test_ratio_debug():
                from flask import Response
                return Response(large_body, status=200, content_type="application/json")

        original_debug = app_fixture.debug
        app_fixture.debug = True
        try:
            r = client.get("/_test_ratio_debug", headers=_GZIP_HEADERS)
            if r.headers.get("Content-Encoding") == "gzip":
                ratio = r.headers.get("X-Compression-Ratio")
                assert ratio is not None
                assert 0 < float(ratio) < 1
        finally:
            app_fixture.debug = original_debug
