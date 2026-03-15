"""Tests for smart caching strategy."""

import json
import time
import pytest

from app.services.smart_cache import (
    L1Cache,
    _make_cache_key,
    cache_get,
    cache_set,
    cache_delete,
    cache_invalidate_user,
    cache_invalidate_all,
    get_cache_stats,
    reset_cache_stats,
    warm_cache_for_user,
    cached,
    _l1_cache,
    CACHE_POLICIES,
)


# ─── L1 Cache Tests ─────────────────────────────────────────────────


class TestL1Cache:
    def test_set_and_get(self):
        cache = L1Cache()
        cache.set("key1", "value1", ttl=60)
        assert cache.get("key1") == "value1"

    def test_get_missing(self):
        cache = L1Cache()
        assert cache.get("nonexistent") is None

    def test_delete(self):
        cache = L1Cache()
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_clear(self):
        cache = L1Cache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_invalidate_prefix(self):
        cache = L1Cache()
        cache.set("dash:user:1:a", "v1")
        cache.set("dash:user:1:b", "v2")
        cache.set("cat:user:1:c", "v3")
        cache.invalidate_prefix("dash:user:1")
        assert cache.get("dash:user:1:a") is None
        assert cache.get("dash:user:1:b") is None
        assert cache.get("cat:user:1:c") == "v3"

    def test_eviction_on_max_size(self):
        cache = L1Cache(max_size=3)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")
        # This should trigger eviction
        cache.set("k4", "v4")
        assert cache.get("k4") == "v4"
        # Size should not exceed max
        assert len(cache._store) <= 3

    def test_stats(self):
        cache = L1Cache()
        cache.set("key1", "value1")
        cache.get("key1")     # hit
        cache.get("missing")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_stats_empty(self):
        cache = L1Cache()
        stats = cache.stats()
        assert stats["hit_rate"] == 0

    def test_expired_entry(self):
        cache = L1Cache()
        cache.set("key1", "value1", ttl=0)
        # TTL of 0 means it expires at time.time() + 0 = now
        # Due to timing, force expiry
        cache._store["key1"] = ("value1", time.time() - 1)
        assert cache.get("key1") is None


# ─── Cache Key Generation Tests ─────────────────────────────────────


class TestCacheKey:
    def test_basic_key(self):
        key = _make_cache_key("dash", 1)
        assert key == "dash:user:1"

    def test_key_with_params(self):
        key = _make_cache_key("dash", 1, {"month": "2026-03"})
        assert key.startswith("dash:user:1:")
        assert len(key) > len("dash:user:1:")

    def test_same_params_same_key(self):
        k1 = _make_cache_key("dash", 1, {"a": 1, "b": 2})
        k2 = _make_cache_key("dash", 1, {"b": 2, "a": 1})
        assert k1 == k2  # Sorted params = deterministic

    def test_different_params_different_key(self):
        k1 = _make_cache_key("dash", 1, {"month": "2026-03"})
        k2 = _make_cache_key("dash", 1, {"month": "2026-04"})
        assert k1 != k2

    def test_different_users_different_key(self):
        k1 = _make_cache_key("dash", 1)
        k2 = _make_cache_key("dash", 2)
        assert k1 != k2


# ─── Cache Operations Tests ─────────────────────────────────────────


class TestCacheOperations:
    def setup_method(self):
        _l1_cache.clear()

    def test_set_and_get(self):
        cache_set("test:key1", {"data": "hello"}, ttl=60)
        result = cache_get("test:key1")
        assert result == {"data": "hello"}

    def test_get_missing(self):
        assert cache_get("nonexistent:key") is None

    def test_delete(self):
        cache_set("test:key2", "value", ttl=60)
        cache_delete("test:key2")
        # L1 should be cleared
        assert _l1_cache.get("test:key2") is None

    def test_invalidate_user(self):
        cache_set("dash:user:1:a", "v1", ttl=60)
        cache_set("dash:user:1:b", "v2", ttl=60)
        cache_invalidate_user(1, ["dashboard"])
        assert _l1_cache.get("dash:user:1:a") is None
        assert _l1_cache.get("dash:user:1:b") is None

    def test_invalidate_all(self):
        cache_set("dash:user:1", "v1", ttl=60)
        cache_set("cat:user:2", "v2", ttl=60)
        cache_invalidate_all()
        assert _l1_cache.get("dash:user:1") is None
        assert _l1_cache.get("cat:user:2") is None

    def test_invalidate_specific_types(self):
        cache_set("dash:user:1:x", "dashboard_data", ttl=60)
        cache_set("cat:user:1:y", "category_data", ttl=60)
        cache_invalidate_user(1, ["dashboard"])
        assert _l1_cache.get("dash:user:1:x") is None
        assert _l1_cache.get("cat:user:1:y") == "category_data"


# ─── Cached Decorator Tests ─────────────────────────────────────────


class TestCachedDecorator:
    def setup_method(self):
        _l1_cache.clear()

    def test_caches_result(self):
        call_count = 0

        @cached(data_type="dashboard")
        def get_dashboard(user_id):
            nonlocal call_count
            call_count += 1
            return {"total": 1000}

        result1 = get_dashboard(1)
        result2 = get_dashboard(1)
        assert result1 == {"total": 1000}
        assert result2 == {"total": 1000}
        assert call_count == 1  # Only called once

    def test_different_users_separate_cache(self):
        call_count = 0

        @cached(data_type="dashboard")
        def get_dashboard(user_id):
            nonlocal call_count
            call_count += 1
            return {"user": user_id}

        result1 = get_dashboard(1)
        result2 = get_dashboard(2)
        assert result1 == {"user": 1}
        assert result2 == {"user": 2}
        assert call_count == 2

    def test_none_not_cached(self):
        call_count = 0

        @cached(data_type="dashboard")
        def get_data(user_id):
            nonlocal call_count
            call_count += 1
            return None

        get_data(1)
        get_data(1)
        assert call_count == 2  # Called each time since None isn't cached

    def test_with_key_params(self):
        call_count = 0

        @cached(data_type="analytics", key_params=["month"])
        def get_analytics(user_id, month=None):
            nonlocal call_count
            call_count += 1
            return {"month": month}

        get_analytics(1, month="2026-03")
        get_analytics(1, month="2026-03")
        get_analytics(1, month="2026-04")
        assert call_count == 2  # Different month = different cache


# ─── Cache Warming Tests ────────────────────────────────────────────


class TestCacheWarming:
    def setup_method(self):
        _l1_cache.clear()

    def test_warm_with_warmers(self):
        def dashboard_warmer(user_id):
            return {"total": 500}

        results = warm_cache_for_user(1, {"dashboard": dashboard_warmer})
        assert results["dashboard"]["status"] == "warmed"

    def test_warm_empty_result(self):
        def empty_warmer(user_id):
            return None

        results = warm_cache_for_user(1, {"dashboard": empty_warmer})
        assert results["dashboard"]["status"] == "empty"

    def test_warm_error_handling(self):
        def failing_warmer(user_id):
            raise ValueError("test error")

        results = warm_cache_for_user(1, {"dashboard": failing_warmer})
        assert results["dashboard"]["status"] == "error"

    def test_warm_no_warmers(self):
        results = warm_cache_for_user(1)
        assert results == {}


# ─── Statistics Tests ────────────────────────────────────────────────


class TestCacheStats:
    def test_get_stats(self):
        stats = get_cache_stats()
        assert "l1_cache" in stats
        assert "l2_cache" in stats
        assert "policies" in stats

    def test_reset_stats(self):
        _l1_cache.set("k", "v")
        _l1_cache.get("k")  # Hit
        reset_cache_stats()
        stats = _l1_cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


# ─── Route Tests ────────────────────────────────────────────────────


class TestCacheRoutes:
    def test_get_stats(self, client, auth_header):
        resp = client.get("/cache/stats", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "l1_cache" in data
        assert "l2_cache" in data

    def test_reset_stats(self, client, auth_header):
        resp = client.post("/cache/stats/reset", headers=auth_header)
        assert resp.status_code == 200

    def test_list_policies(self, client, auth_header):
        resp = client.get("/cache/policies", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "policies" in data
        assert "dashboard" in data["policies"]
        assert data["policies"]["dashboard"]["ttl_seconds"] == 300

    def test_invalidate_user(self, client, auth_header):
        resp = client.post("/cache/invalidate/user", headers=auth_header)
        assert resp.status_code == 200

    def test_invalidate_user_specific_types(self, client, auth_header):
        resp = client.post("/cache/invalidate/user", headers=auth_header,
                           json={"data_types": ["dashboard", "analytics"]})
        assert resp.status_code == 200

    def test_invalidate_all(self, client, auth_header):
        resp = client.post("/cache/invalidate/all", headers=auth_header)
        assert resp.status_code == 200

    def test_warm_cache(self, client, auth_header):
        resp = client.post("/cache/warm", headers=auth_header)
        assert resp.status_code == 200

    def test_test_cache_set(self, client, auth_header):
        resp = client.post("/cache/test", headers=auth_header,
                           json={"key": "mykey", "value": "myvalue", "operation": "set"})
        assert resp.status_code == 200
        assert "Cached" in resp.get_json()["message"]

    def test_test_cache_get(self, client, auth_header):
        # Set then get
        client.post("/cache/test", headers=auth_header,
                    json={"key": "mykey2", "value": {"data": 42}, "operation": "set"})
        resp = client.get_json if False else client.post(
            "/cache/test", headers=auth_header,
            json={"key": "mykey2", "operation": "get"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is True
        assert data["value"] == {"data": 42}

    def test_test_cache_delete(self, client, auth_header):
        client.post("/cache/test", headers=auth_header,
                    json={"key": "delkey", "value": "v", "operation": "set"})
        resp = client.post("/cache/test", headers=auth_header,
                           json={"key": "delkey", "operation": "delete"})
        assert resp.status_code == 200

    def test_test_cache_missing_key(self, client, auth_header):
        resp = client.post("/cache/test", headers=auth_header, json={"operation": "set"})
        assert resp.status_code == 400

    def test_test_cache_set_missing_value(self, client, auth_header):
        resp = client.post("/cache/test", headers=auth_header,
                           json={"key": "k", "operation": "set"})
        assert resp.status_code == 400

    def test_test_cache_unknown_operation(self, client, auth_header):
        resp = client.post("/cache/test", headers=auth_header,
                           json={"key": "k", "operation": "unknown"})
        assert resp.status_code == 400

    def test_cache_health(self, client, auth_header):
        resp = client.get("/cache/health", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "l1_cache" in data
        assert "l2_cache" in data
        assert data["l1_cache"]["status"] == "healthy"


class TestCacheAuth:
    def test_stats_requires_auth(self, client):
        resp = client.get("/cache/stats")
        assert resp.status_code in (401, 422)

    def test_policies_requires_auth(self, client):
        resp = client.get("/cache/policies")
        assert resp.status_code in (401, 422)
