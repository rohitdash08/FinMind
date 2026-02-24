"""Tests for smart caching strategy (#127)."""

import time
from app.services.cache import (
    cache_get, cache_set, cache_delete, invalidate_tag,
    invalidate_user, cache_stats, clear_all, _cache, _tag_keys,
)


class TestCacheCore:
    def setup_method(self):
        clear_all()

    def test_set_and_get(self):
        cache_set("k1", {"data": 1}, ttl=60)
        assert cache_get("k1") == {"data": 1}

    def test_miss(self):
        assert cache_get("nonexistent") is None

    def test_expiry(self):
        cache_set("k2", "val", ttl=0)
        time.sleep(0.01)
        assert cache_get("k2") is None

    def test_delete(self):
        cache_set("k3", "val", ttl=60, tags=["t1"])
        cache_delete("k3")
        assert cache_get("k3") is None

    def test_tag_invalidation(self):
        cache_set("a1", "v1", ttl=60, tags=["group1"])
        cache_set("a2", "v2", ttl=60, tags=["group1"])
        cache_set("a3", "v3", ttl=60, tags=["group2"])
        invalidate_tag("group1")
        assert cache_get("a1") is None
        assert cache_get("a2") is None
        assert cache_get("a3") == "v3"

    def test_user_invalidation(self):
        cache_set("u1", "data", ttl=60, tags=["user:42"])
        cache_set("u2", "data", ttl=60, tags=["user:42"])
        cache_set("u3", "other", ttl=60, tags=["user:99"])
        invalidate_user(42)
        assert cache_get("u1") is None
        assert cache_get("u2") is None
        assert cache_get("u3") == "other"

    def test_stats(self):
        cache_set("s1", "v", ttl=60, tags=["t"])
        cache_set("s2", "v", ttl=0, tags=["t"])
        time.sleep(0.01)
        stats = cache_stats()
        assert stats["total_entries"] == 2
        assert stats["active"] == 1
        assert stats["expired"] == 1

    def test_clear_all(self):
        cache_set("c1", "v", ttl=60)
        clear_all()
        assert cache_get("c1") is None
        assert len(_cache) == 0
        assert len(_tag_keys) == 0


class TestCacheAPI:
    def test_stats_endpoint(self, client, auth_header):
        r = client.get("/cache/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "total_entries" in data

    def test_invalidate_endpoint(self, client, auth_header):
        r = client.post("/cache/invalidate", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "invalidated"

    def test_clear_endpoint(self, client, auth_header):
        r = client.post("/cache/clear", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "cleared"
