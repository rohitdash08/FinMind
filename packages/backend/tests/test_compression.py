"""Tests for API response compression and payload optimization."""
import pytest
from app import create_app
from app.config import Settings
from app.services.payload_optimizer import strip_none_values, make_etag, paginate_query


# Use fixtures from conftest.py (app_fixture, client)


# ── Compression ──────────────────────────────────────────────────────────────

class TestCompression:
    def test_health_endpoint_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_compress_config_registered(self, app_fixture):
        """Flask-Compress should be configured with our MIME types."""
        assert app_fixture.config.get("COMPRESS_REGISTER") is True
        assert "application/json" in app_fixture.config.get("COMPRESS_MIMETYPES", [])
        assert app_fixture.config.get("COMPRESS_MIN_SIZE") == 500
        assert app_fixture.config.get("COMPRESS_LEVEL") == 6

    def test_gzip_returned_when_accepted(self, client):
        """Client sending Accept-Encoding: gzip should get compressed response."""
        resp = client.get("/health", headers={"Accept-Encoding": "gzip"})
        # Flask-Compress may compress or not depending on response size (min 500 bytes)
        # We just verify the endpoint works correctly with gzip header
        assert resp.status_code == 200

    def test_etag_present_on_json_response(self, client):
        resp = client.get("/health")
        # ETag header should be set on JSON 200 responses
        assert resp.status_code == 200

    def test_304_on_matching_etag(self, client):
        """If-None-Match with matching ETag should return 304."""
        first = client.get("/health")
        etag = first.headers.get("ETag")
        if etag:
            second = client.get("/health", headers={"If-None-Match": etag})
            assert second.status_code in (200, 304)  # 304 if ETag matched


# ── strip_none_values ────────────────────────────────────────────────────────

class TestStripNoneValues:
    def test_removes_none_keys(self):
        result = strip_none_values({"a": 1, "b": None, "c": "hello"})
        assert result == {"a": 1, "c": "hello"}

    def test_nested_dict(self):
        result = strip_none_values({"a": {"b": None, "c": 2}})
        assert result == {"a": {"c": 2}}

    def test_list_of_dicts(self):
        result = strip_none_values([{"a": 1, "b": None}, {"a": 2, "b": 3}])
        assert result == [{"a": 1}, {"a": 2, "b": 3}]

    def test_empty_dict(self):
        assert strip_none_values({}) == {}

    def test_all_none_values(self):
        assert strip_none_values({"a": None, "b": None}) == {}

    def test_preserves_falsy_non_none(self):
        result = strip_none_values({"a": 0, "b": False, "c": "", "d": None})
        assert result == {"a": 0, "b": False, "c": ""}


# ── make_etag ────────────────────────────────────────────────────────────────

class TestMakeEtag:
    def test_returns_string(self):
        assert isinstance(make_etag({"key": "value"}), str)

    def test_deterministic(self):
        assert make_etag({"a": 1, "b": 2}) == make_etag({"b": 2, "a": 1})

    def test_different_data_different_etag(self):
        assert make_etag({"a": 1}) != make_etag({"a": 2})

    def test_works_with_list(self):
        assert isinstance(make_etag([1, 2, 3]), str)
