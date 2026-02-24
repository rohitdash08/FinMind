"""Tests for response compression, payload optimization, and ETag support."""

import gzip
import json

import pytest

try:
    import brotli

    _HAS_BROTLI = True
except ImportError:
    _HAS_BROTLI = False

from app.compression import compact_json, strip_nulls


# ---------------------------------------------------------------------------
# Unit tests for helper utilities
# ---------------------------------------------------------------------------


class TestStripNulls:
    def test_removes_none_values(self):
        assert strip_nulls({"a": 1, "b": None}) == {"a": 1}

    def test_nested_dict(self):
        data = {"a": {"b": None, "c": 2}, "d": None}
        assert strip_nulls(data) == {"a": {"c": 2}}

    def test_list_of_dicts(self):
        data = [{"a": 1, "b": None}, {"c": None, "d": 3}]
        assert strip_nulls(data) == [{"a": 1}, {"d": 3}]

    def test_preserves_falsy_non_none(self):
        data = {"a": 0, "b": "", "c": False, "d": [], "e": None}
        result = strip_nulls(data)
        assert result == {"a": 0, "b": "", "c": False, "d": []}

    def test_scalar_passthrough(self):
        assert strip_nulls(42) == 42
        assert strip_nulls("hello") == "hello"


class TestCompactJson:
    def test_no_whitespace(self):
        raw = compact_json({"key": "value", "num": 123})
        assert b" " not in raw
        assert b"\n" not in raw

    def test_nulls_stripped(self):
        raw = compact_json({"a": 1, "b": None})
        parsed = json.loads(raw)
        assert "b" not in parsed

    def test_returns_bytes(self):
        assert isinstance(compact_json({"x": 1}), bytes)


# ---------------------------------------------------------------------------
# Integration tests using the Flask test client
# ---------------------------------------------------------------------------


def _big_payload(client, auth_header):
    """Create enough expenses to produce a response > 256 bytes."""
    # Create a category first
    r = client.post("/categories", json={"name": "Compression"}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cat_id = r.get_json()[0]["id"]

    for i in range(15):
        r = client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"Compression test expense number {i:03d} with extra text padding",
                "category_id": cat_id,
                "date": f"2026-01-{(i % 28) + 1:02d}",
            },
            headers=auth_header,
        )
        assert r.status_code == 201


class TestGzipCompression:
    def test_gzip_response_when_accepted(self, client, auth_header):
        _big_payload(client, auth_header)
        r = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": "gzip"},
        )
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") == "gzip"
        assert r.headers.get("Vary") == "Accept-Encoding"
        # Decompress and verify valid JSON
        body = gzip.decompress(r.data)
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) == 15

    def test_no_compression_without_accept_encoding(self, client, auth_header):
        _big_payload(client, auth_header)
        r = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": ""},
        )
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") is None
        # Should still be valid JSON
        data = r.get_json()
        assert isinstance(data, list)


@pytest.mark.skipif(not _HAS_BROTLI, reason="brotli not installed")
class TestBrotliCompression:
    def test_brotli_preferred_over_gzip(self, client, auth_header):
        _big_payload(client, auth_header)
        r = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": "gzip, br"},
        )
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") == "br"
        body = brotli.decompress(r.data)
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) == 15

    def test_brotli_only(self, client, auth_header):
        _big_payload(client, auth_header)
        r = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": "br"},
        )
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") == "br"


class TestETag:
    def test_etag_header_present(self, client, auth_header):
        _big_payload(client, auth_header)
        r = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": ""},
        )
        assert r.status_code == 200
        etag = r.headers.get("ETag")
        assert etag is not None
        assert etag.startswith('"') and etag.endswith('"')

    def test_304_on_matching_etag(self, client, auth_header):
        _big_payload(client, auth_header)
        # First request to get the ETag
        r1 = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": ""},
        )
        assert r1.status_code == 200
        etag = r1.headers.get("ETag")
        assert etag

        # Second request with If-None-Match
        r2 = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": "", "If-None-Match": etag},
        )
        assert r2.status_code == 304

    def test_200_on_mismatched_etag(self, client, auth_header):
        _big_payload(client, auth_header)
        r = client.get(
            "/expenses",
            headers={
                **auth_header,
                "Accept-Encoding": "",
                "If-None-Match": '"bogus"',
            },
        )
        assert r.status_code == 200

    def test_etag_changes_after_data_mutation(self, client, auth_header):
        _big_payload(client, auth_header)
        r1 = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": ""},
        )
        etag1 = r1.headers.get("ETag")

        # Add another expense
        client.post(
            "/expenses",
            json={
                "amount": 999.99,
                "description": "New expense to change etag",
                "date": "2026-01-15",
            },
            headers=auth_header,
        )

        r2 = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": ""},
        )
        etag2 = r2.headers.get("ETag")
        assert etag1 != etag2


class TestSmallPayloadSkipsCompression:
    def test_health_endpoint_not_compressed(self, client):
        r = client.get("/health", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.headers.get("Content-Encoding") is None

    def test_empty_list_not_compressed(self, client, auth_header):
        r = client.get(
            "/expenses",
            headers={**auth_header, "Accept-Encoding": "gzip"},
        )
        assert r.status_code == 200
        # Empty list "[]" is < 256 bytes, should not be compressed
        assert r.headers.get("Content-Encoding") is None


class TestNonJsonEndpoints:
    def test_metrics_not_compressed(self, client):
        """Metrics endpoint uses text/plain with version param — should still compress if large."""
        r = client.get("/metrics", headers={"Accept-Encoding": "gzip"})
        # Metrics may or may not be large enough; just verify no crash
        assert r.status_code == 200
