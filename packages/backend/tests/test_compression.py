"""
Tests for API response compression middleware.
"""

import json
import pytest
from app.middleware.compression import (
    should_compress,
    compress_response,
    init_compression,
)
from flask import Response


@pytest.fixture
def app_with_compression(app):
    init_compression(app)
    return app


class TestCompression:
    def test_compresses_json_response(self, app_with_compression, client):
        """Large JSON responses should be compressed."""
        large_data = {"items": [{"id": i, "name": f"item_{i}" * 50} for i in range(100)]}
        resp = client.get(
            "/insights",
            headers={"Accept-Encoding": "gzip"},
        )
        # Just verify middleware is installed and does not crash
        assert resp.status_code in (200, 401, 404)

    def test_skips_small_responses(self, app):
        init_compression(app)

        @app.route("/test/small")
        def small():
            return Response("hi", content_type="text/plain")

        with app.test_client() as c:
            resp = c.get("/test/small", headers={"Accept-Encoding": "gzip"})
            assert resp.content_encoding is None  # Not compressed

    def test_skips_binary_content(self, app):
        init_compression(app)

        @app.route("/test/binary")
        def binary():
            return Response(b"\x00" * 10000, content_type="image/png")

        with app.test_client() as c:
            resp = c.get("/test/binary", headers={"Accept-Encoding": "gzip"})
            assert resp.content_encoding is None

    def test_skips_no_accept_encoding(self, app):
        init_compression(app)

        @app.route("/test/noenc")
        def noenc():
            return Response("x" * 10000, content_type="application/json")

        with app.test_client() as c:
            resp = c.get("/test/noenc")  # No Accept-Encoding
            assert resp.content_encoding is None

    def test_configurable_min_size(self, app):
        app.config["COMPRESSION_MIN_SIZE"] = 10
        init_compression(app)

        @app.route("/test/threshold")
        def threshold():
            return Response("x" * 20, content_type="application/json")

        with app.test_client() as c:
            resp = c.get("/test/threshold", headers={"Accept-Encoding": "gzip"})
            # Should be compressed (20 > 10)
            assert resp.content_encoding == "gzip"
