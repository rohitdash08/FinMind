"""Tests for smart caching strategy."""

import time
import pytest
from app.services.smart_cache import InMemoryCache, SmartCache, cache_key


class TestInMemoryCache:
    def test_set_and_get(self):
        c = InMemoryCache()
        c.set("k1", {"data": 1}, ttl=60)
        assert c.get("k1") == {"data": 1}

    def test_get_missing(self):
        c = InMemoryCache()
        assert c.get("missing") is None

    def test_ttl_expiry(self):
        c = InMemoryCache()
        c.set("k1", "val", ttl=1)
        assert c.get("k1") == "val"
        time.sleep(1.1)
        assert c.get("k1") is None

    def test_lru_eviction(self):
        c = InMemoryCache(max_size=3)
        c.set("a", 1, ttl=60)
        c.set("b", 2, ttl=60)
        c.set("c", 3, ttl=60)
        c.set("d", 4, ttl=60)  # evicts "a"
        assert c.get("a") is None
        assert c.get("d") == 4

    def test_invalidate_pattern(self):
        c = InMemoryCache()
        c.set("user:1:dashboard", "d1", ttl=60)
        c.set("user:1:analytics", "a1", ttl=60)
        c.set("user:2:dashboard", "d2", ttl=60)
        c.invalidate_pattern("user:1")
        assert c.get("user:1:dashboard") is None
        assert c.get("user:1:analytics") is None
        assert c.get("user:2:dashboard") == "d2"

    def test_clear(self):
        c = InMemoryCache()
        c.set("a", 1, ttl=60)
        c.set("b", 2, ttl=60)
        c.clear()
        assert c.get("a") is None
        assert c.get("b") is None

    def test_stats(self):
        c = InMemoryCache(max_size=100)
        c.set("a", 1, ttl=60)
        c.set("b", 2, ttl=60)
        s = c.stats()
        assert s["total_entries"] == 2
        assert s["max_size"] == 100


class TestSmartCache:
    def test_set_get(self):
        sc = SmartCache()
        sc.set("test:key", {"val": 42}, ttl=60)
        assert sc.get("test:key") == {"val": 42}

    def test_miss(self):
        sc = SmartCache()
        assert sc.get("nonexistent") is None

    def test_invalidation_expense(self):
        sc = SmartCache()
        sc.set("user:1:dashboard:main", "data", ttl=60)
        sc.set("user:1:analytics:monthly", "data", ttl=60)
        sc.set("user:1:categories:all", "data", ttl=60)
        sc.invalidate("expense_created", user_id=1)
        assert sc.get("user:1:dashboard:main") is None
        assert sc.get("user:1:analytics:monthly") is None
        assert sc.get("user:1:categories:all") == "data"  # not invalidated

    def test_invalidation_bill(self):
        sc = SmartCache()
        sc.set("user:1:dashboard:x", "d", ttl=60)
        sc.set("user:1:bills:upcoming", "b", ttl=60)
        sc.invalidate("bill_created", user_id=1)
        assert sc.get("user:1:dashboard:x") is None
        assert sc.get("user:1:bills:upcoming") is None

    def test_stats(self):
        sc = SmartCache()
        sc.set("k", "v", ttl=60)
        sc.get("k")  # hit
        sc.get("miss")  # miss
        s = sc.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["backend"] == "memory"

    def test_clear_all(self):
        sc = SmartCache()
        sc.set("a", 1, ttl=60)
        sc.clear_all()
        assert sc.get("a") is None

    def test_auto_ttl_from_prefix(self):
        sc = SmartCache()
        sc.set("dashboard:main", "data")  # should use 120s TTL
        assert sc.get("dashboard:main") == "data"


class TestCacheKey:
    def test_basic(self):
        assert cache_key("user:1", "dashboard") == "finmind:user:1:dashboard"

    def test_with_numbers(self):
        assert cache_key("user", 1, "page", 2) == "finmind:user:1:page:2"


class TestCacheAPI:
    def test_stats(self, client):
        resp = client.get("/cache/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "backend" in data
        assert "hits" in data

    def test_invalidate(self, client):
        resp = client.post("/cache/invalidate", json={"event": "expense_created", "user_id": 1})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_invalidate_missing_event(self, client):
        resp = client.post("/cache/invalidate", json={})
        assert resp.status_code == 400

    def test_clear(self, client):
        resp = client.post("/cache/clear")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
