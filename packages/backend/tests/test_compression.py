"""Tests for API response compression and payload optimization."""

import gzip
import json
import pytest
from flask import Flask, jsonify
from app.middleware.compression import (
    init_compression,
    slim_response,
    _filter_payload,
    add_pagination_headers,
)


@pytest.fixture
def compression_app():
    """Create a test app with compression enabled."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    init_compression(app, minimum_size=50, compression_level=6)

    @app.route("/large")
    def large_response():
        data = {"items": [{"id": i, "name": f"item_{i}", "value": i * 100} for i in range(100)]}
        return jsonify(data)

    @app.route("/small")
    def small_response():
        return jsonify({"ok": True})

    @app.route("/error")
    def error_response():
        return jsonify({"error": "not found"}), 404

    return app


@pytest.fixture
def comp_client(compression_app):
    return compression_app.test_client()


class TestGzipCompression:
    def test_compresses_large_response(self, comp_client):
        resp = comp_client.get("/large", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        assert resp.headers.get("Content-Encoding") == "gzip"
        decompressed = gzip.decompress(resp.data)
        data = json.loads(decompressed)
        assert len(data["items"]) == 100

    def test_no_compression_without_header(self, comp_client):
        resp = comp_client.get("/large")
        assert resp.headers.get("Content-Encoding") is None
        data = resp.get_json()
        assert len(data["items"]) == 100

    def test_no_compression_small_response(self, comp_client):
        resp = comp_client.get("/small", headers={"Accept-Encoding": "gzip"})
        assert resp.headers.get("Content-Encoding") is None
        assert resp.get_json() == {"ok": True}

    def test_no_compression_error_response(self, comp_client):
        resp = comp_client.get("/error", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 404
        assert resp.headers.get("Content-Encoding") is None

    def test_compressed_smaller_than_original(self, comp_client):
        resp_plain = comp_client.get("/large")
        resp_gzip = comp_client.get("/large", headers={"Accept-Encoding": "gzip"})
        assert len(resp_gzip.data) < len(resp_plain.data)


class TestPayloadFiltering:
    def test_filter_fields(self):
        data = {"id": 1, "name": "test", "secret": "hidden"}
        result = _filter_payload(data, fields={"id", "name"}, exclude=set())
        assert result == {"id": 1, "name": "test"}

    def test_filter_exclude(self):
        data = {"id": 1, "name": "test", "secret": "hidden"}
        result = _filter_payload(data, fields=None, exclude={"secret"})
        assert result == {"id": 1, "name": "test"}

    def test_filter_list(self):
        data = [
            {"id": 1, "name": "a", "extra": "x"},
            {"id": 2, "name": "b", "extra": "y"},
        ]
        result = _filter_payload(data, fields={"id", "name"}, exclude=set())
        assert result == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

    def test_filter_empty_fields(self):
        data = {"id": 1, "name": "test"}
        result = _filter_payload(data, fields=None, exclude=set())
        assert result == {"id": 1, "name": "test"}

    def test_filter_non_dict(self):
        assert _filter_payload("string", None, set()) == "string"
        assert _filter_payload(42, None, set()) == 42


class TestPaginationHeaders:
    def test_pagination_headers(self, compression_app):
        with compression_app.test_request_context():
            from flask import make_response
            resp = make_response(jsonify([]))
            add_pagination_headers(resp, page=2, per_page=20, total=95)
            assert resp.headers["X-Page"] == "2"
            assert resp.headers["X-Per-Page"] == "20"
            assert resp.headers["X-Total"] == "95"
            assert resp.headers["X-Total-Pages"] == "5"

    def test_pagination_single_page(self, compression_app):
        with compression_app.test_request_context():
            from flask import make_response
            resp = make_response(jsonify([]))
            add_pagination_headers(resp, page=1, per_page=50, total=10)
            assert resp.headers["X-Total-Pages"] == "1"
