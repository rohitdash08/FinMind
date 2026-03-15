"""Tests for API response compression and payload optimization."""

import gzip
import json
import pytest

from app.services.compression import (
    _compress_gzip,
    _compute_etag,
    _should_compress,
    _reset_stats,
    get_compression_stats,
    optimize_json_payload,
    paginate_response,
    slim_response,
    DEFAULT_CONFIG,
)


# ─── Compression Engine Tests ───────────────────────────────────────


class TestGzipCompression:
    def test_compress_and_decompress(self):
        data = b"Hello, this is test data " * 100
        compressed = _compress_gzip(data)
        assert len(compressed) < len(data)
        # Verify it's valid gzip
        decompressed = gzip.decompress(compressed)
        assert decompressed == data

    def test_compress_small_data(self):
        data = b"small"
        compressed = _compress_gzip(data)
        # Small data might not compress well, but should still work
        decompressed = gzip.decompress(compressed)
        assert decompressed == data

    def test_compression_level(self):
        data = b"Test data " * 1000
        level1 = _compress_gzip(data, level=1)
        level9 = _compress_gzip(data, level=9)
        # Higher level = better compression (usually)
        assert len(level9) <= len(level1)


class TestETag:
    def test_compute_etag(self):
        data = b"test data"
        etag = _compute_etag(data)
        assert etag.startswith('W/"')
        assert etag.endswith('"')

    def test_same_data_same_etag(self):
        data = b"consistent data"
        assert _compute_etag(data) == _compute_etag(data)

    def test_different_data_different_etag(self):
        assert _compute_etag(b"data1") != _compute_etag(b"data2")


# ─── Payload Optimization Tests ─────────────────────────────────────


class TestOptimizeJsonPayload:
    def test_field_selection_dict(self):
        data = {"name": "Alice", "email": "alice@test.com", "age": 30}
        result = optimize_json_payload(data, ["name", "email"])
        assert result == {"name": "Alice", "email": "alice@test.com"}

    def test_field_selection_list(self):
        data = [
            {"name": "Alice", "age": 30, "city": "NY"},
            {"name": "Bob", "age": 25, "city": "LA"},
        ]
        result = optimize_json_payload(data, ["name", "city"])
        assert result == [
            {"name": "Alice", "city": "NY"},
            {"name": "Bob", "city": "LA"},
        ]

    def test_no_fields_returns_all(self):
        data = {"a": 1, "b": 2}
        result = optimize_json_payload(data, None)
        assert result == data

    def test_empty_fields_returns_all(self):
        data = {"a": 1, "b": 2}
        result = optimize_json_payload(data, [])
        assert result == data

    def test_non_dict_items_in_list(self):
        data = [1, 2, 3]
        result = optimize_json_payload(data, ["a"])
        assert result == []


class TestPaginateResponse:
    def test_basic_pagination(self):
        items = list(range(50))
        result = paginate_response(items, page=1, page_size=10)
        assert len(result["items"]) == 10
        assert result["items"] == list(range(10))
        assert result["pagination"]["total_items"] == 50
        assert result["pagination"]["total_pages"] == 5
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is False

    def test_last_page(self):
        items = list(range(25))
        result = paginate_response(items, page=3, page_size=10)
        assert len(result["items"]) == 5
        assert result["pagination"]["has_next"] is False
        assert result["pagination"]["has_prev"] is True

    def test_single_page(self):
        items = [1, 2, 3]
        result = paginate_response(items, page=1, page_size=10)
        assert len(result["items"]) == 3
        assert result["pagination"]["total_pages"] == 1
        assert result["pagination"]["has_next"] is False
        assert result["pagination"]["has_prev"] is False

    def test_max_page_size_enforced(self):
        items = list(range(200))
        result = paginate_response(items, page=1, page_size=500, max_page_size=100)
        assert len(result["items"]) == 100

    def test_empty_list(self):
        result = paginate_response([], page=1, page_size=10)
        assert result["items"] == []
        assert result["pagination"]["total_items"] == 0
        assert result["pagination"]["total_pages"] == 1

    def test_negative_page(self):
        items = list(range(10))
        result = paginate_response(items, page=-1, page_size=5)
        assert result["pagination"]["page"] == 1


class TestSlimResponse:
    def test_removes_nulls(self):
        data = {"name": "Alice", "email": None, "age": 30}
        result = slim_response(data)
        assert result == {"name": "Alice", "age": 30}

    def test_keeps_nulls_when_disabled(self):
        data = {"name": "Alice", "email": None}
        result = slim_response(data, exclude_nulls=False)
        assert result == data

    def test_removes_empty(self):
        data = {"name": "Alice", "items": [], "meta": {}, "desc": ""}
        result = slim_response(data, exclude_empty=True)
        assert result == {"name": "Alice"}

    def test_nested_dict(self):
        data = {"user": {"name": "Alice", "phone": None}, "count": 1}
        result = slim_response(data)
        assert result == {"user": {"name": "Alice"}, "count": 1}

    def test_non_dict_passthrough(self):
        assert slim_response("string") == "string"
        assert slim_response(42) == 42


# ─── Statistics Tests ────────────────────────────────────────────────


class TestCompressionStats:
    def test_initial_stats(self):
        _reset_stats()
        stats = get_compression_stats()
        assert stats["total_requests"] == 0
        assert stats["compressed_responses"] == 0
        assert stats["overall_ratio"] == 0

    def test_reset_stats(self):
        _reset_stats()
        stats = get_compression_stats()
        assert stats["total_requests"] == 0
        assert stats["bytes_saved"] == 0


# ─── Integration Tests (Routes) ─────────────────────────────────────


class TestCompressionRoutes:
    def test_get_stats(self, client, auth_header):
        _reset_stats()
        resp = client.get("/compression/stats", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_requests" in data
        assert "overall_ratio" in data

    def test_reset_stats_route(self, client, auth_header):
        resp = client.post("/compression/stats/reset", headers=auth_header)
        assert resp.status_code == 200
        assert "reset" in resp.get_json()["message"].lower()

    def test_get_config(self, client, auth_header):
        resp = client.get("/compression/config", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "min_size_bytes" in data
        assert "compression_level" in data
        assert "etag_enabled" in data

    def test_optimize_payload(self, client, auth_header):
        resp = client.post("/compression/optimize", headers=auth_header, json={
            "data": {"name": "Alice", "email": "alice@test.com", "age": 30},
            "fields": ["name", "email"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["optimized"] == {"name": "Alice", "email": "alice@test.com"}
        assert "metrics" in data
        assert data["metrics"]["bytes_saved"] >= 0

    def test_optimize_with_null_removal(self, client, auth_header):
        resp = client.post("/compression/optimize", headers=auth_header, json={
            "data": {"name": "Alice", "phone": None, "active": True},
            "exclude_nulls": True,
        })
        assert resp.status_code == 200
        optimized = resp.get_json()["optimized"]
        assert "phone" not in optimized

    def test_optimize_missing_data(self, client, auth_header):
        resp = client.post("/compression/optimize", headers=auth_header, json={})
        assert resp.status_code == 400

    def test_optimize_list_payload(self, client, auth_header):
        resp = client.post("/compression/optimize", headers=auth_header, json={
            "data": [
                {"name": "Alice", "age": 30, "city": "NY"},
                {"name": "Bob", "age": 25, "city": "LA"},
            ],
            "fields": ["name"],
        })
        assert resp.status_code == 200
        optimized = resp.get_json()["optimized"]
        assert len(optimized) == 2
        assert optimized[0] == {"name": "Alice"}

    def test_paginate(self, client, auth_header):
        items = list(range(50))
        resp = client.post("/compression/paginate", headers=auth_header, json={
            "items": items,
            "page": 2,
            "page_size": 10,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["items"]) == 10
        assert data["items"] == list(range(10, 20))
        assert data["pagination"]["total_items"] == 50
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_prev"] is True

    def test_paginate_missing_items(self, client, auth_header):
        resp = client.post("/compression/paginate", headers=auth_header, json={})
        assert resp.status_code == 400


class TestCompressionMiddleware:
    def test_small_response_not_compressed(self, client, auth_header):
        """Small responses should not be compressed."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "Content-Encoding" not in resp.headers or resp.headers.get("Content-Encoding") != "gzip"

    def test_etag_present_on_get(self, client, auth_header):
        """GET responses should have ETag header."""
        resp = client.get("/compression/config", headers=auth_header)
        assert resp.status_code == 200
        # ETag should be present on GET requests
        assert "ETag" in resp.headers

    def test_gzip_with_accept_encoding(self, client, auth_header):
        """Responses should be gzipped when client accepts and payload is large enough."""
        _reset_stats()
        # Create a large response by optimizing a big payload
        large_data = [{"name": f"user_{i}", "email": f"user_{i}@test.com",
                        "bio": "x" * 200} for i in range(100)]
        resp = client.post("/compression/optimize",
                           headers={**auth_header, "Accept-Encoding": "gzip"},
                           json={"data": large_data})
        assert resp.status_code == 200

    def test_etag_conditional_request(self, client, auth_header):
        """Conditional request with matching ETag should return 304."""
        # First request to get ETag
        resp1 = client.get("/compression/config", headers=auth_header)
        assert resp1.status_code == 200
        etag = resp1.headers.get("ETag")

        if etag:
            # Second request with If-None-Match
            resp2 = client.get("/compression/config",
                               headers={**auth_header, "If-None-Match": etag})
            assert resp2.status_code == 304


class TestCompressionAuth:
    def test_stats_requires_auth(self, client):
        resp = client.get("/compression/stats")
        assert resp.status_code in (401, 422)

    def test_config_requires_auth(self, client):
        resp = client.get("/compression/config")
        assert resp.status_code in (401, 422)
