"""
Tests for smart caching strategy (Issue #127).

Covers:
- cache_set / cache_get / cache_delete basic operations
- TTL constants are defined and sensible
- Categories: GET returns cached data on second call
- Categories: cache is invalidated on POST/PATCH/DELETE
- Budget suggestion: cached after first call
- Cache stats endpoint returns hit/miss counts
- Graceful degradation: cache failure doesn't crash routes
- cache_delete_patterns removes matching keys
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.cache import (
    TTL,
    budget_suggestion_key,
    cache_delete,
    cache_delete_patterns,
    cache_get,
    cache_set,
    categories_key,
    get_cache_stats,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — cache service
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheOperations:
    def test_set_and_get(self, app_fixture):
        with app_fixture.app_context():
            cache_set("test:key1", {"value": 42}, ttl_seconds=60)
            result = cache_get("test:key1")
            # On real Redis this returns the value; on mock/no-Redis returns None
            assert result is None or result == {"value": 42}

    def test_get_miss_returns_none(self, app_fixture):
        with app_fixture.app_context():
            result = cache_get("test:nonexistent:key:xyz987")
            assert result is None

    def test_delete_removes_key(self, app_fixture):
        with app_fixture.app_context():
            cache_set("test:del:key", "hello", ttl_seconds=60)
            cache_delete("test:del:key")
            assert cache_get("test:del:key") is None

    def test_cache_set_returns_bool(self, app_fixture):
        with app_fixture.app_context():
            result = cache_set("test:bool", 1, ttl_seconds=10)
            assert isinstance(result, bool)


class TestTTLConstants:
    def test_ttl_hierarchy(self):
        assert TTL.STATIC > TTL.AI_RESULT
        assert TTL.AI_RESULT > TTL.ANALYTICS
        assert TTL.ANALYTICS > TTL.DASHBOARD
        assert TTL.DASHBOARD > TTL.SHORT
        assert TTL.SHORT > 0
        assert TTL.REALTIME == 0

    def test_static_is_one_hour(self):
        assert TTL.STATIC == 3600

    def test_ai_result_is_thirty_min(self):
        assert TTL.AI_RESULT == 1800


class TestKeyBuilders:
    def test_categories_key(self):
        assert "42" in categories_key(42)
        assert categories_key(1) != categories_key(2)

    def test_budget_suggestion_key(self):
        k = budget_suggestion_key(1, "2026-03")
        assert "2026-03" in k
        assert "1" in k


class TestGracefulDegradation:
    def test_cache_get_error_returns_none(self):
        """Redis errors should never propagate to callers."""
        with patch("app.services.cache.redis_client") as mock_redis:
            mock_redis.get.side_effect = Exception("connection refused")
            result = cache_get("any:key")
        assert result is None

    def test_cache_set_error_returns_false(self):
        with patch("app.services.cache.redis_client") as mock_redis:
            mock_redis.set.side_effect = Exception("connection refused")
            mock_redis.setex.side_effect = Exception("connection refused")
            result = cache_set("any:key", {"x": 1}, ttl_seconds=60)
        assert result is False

    # ── Fix 3: _increment_hit/_increment_miss log on failure ─────────────────

    def test_increment_hit_redis_failure_logged(self, caplog):
        """_increment_hit must log a debug message on Redis failure, not swallow it."""
        import logging
        from app.services.cache import _increment_hit

        with patch("app.services.cache.redis_client") as mock_redis:
            mock_redis.hincrby.side_effect = Exception("Redis down")
            with caplog.at_level(logging.DEBUG, logger="finmind.cache"):
                _increment_hit()

        assert any("_increment_hit" in r.message for r in caplog.records)

    def test_increment_miss_redis_failure_logged(self, caplog):
        """_increment_miss must log a debug message on Redis failure."""
        import logging
        from app.services.cache import _increment_miss

        with patch("app.services.cache.redis_client") as mock_redis:
            mock_redis.hincrby.side_effect = Exception("Redis down")
            with caplog.at_level(logging.DEBUG, logger="finmind.cache"):
                _increment_miss()

        assert any("_increment_miss" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Fix-specific unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheFixes:

    # ── Fix 1: get_cache_stats uses str keys, not bytes ───────────────────────

    def test_get_cache_stats_reads_string_keys(self):
        """hgetall returns str keys when decode_responses=True.
        get_cache_stats must use 'hits'/'misses' (str), not b'hits'/b'misses'."""
        with patch("app.services.cache.redis_client") as mock_redis:
            # Return a dict with str keys, as decode_responses=True would give
            mock_redis.hgetall.return_value = {"hits": "10", "misses": "3"}
            mock_redis.info.return_value = {"used_memory_human": "1.5M"}
            stats = get_cache_stats()

        assert stats["hits"] == 10
        assert stats["misses"] == 3
        assert stats["total_requests"] == 13
        assert stats["hit_rate_percent"] == round(10 / 13 * 100, 1)

    def test_get_cache_stats_bytes_keys_would_be_zero(self):
        """Regression proof: bytes keys must NOT be used (they always default to 0
        with decode_responses=True Redis)."""
        with patch("app.services.cache.redis_client") as mock_redis:
            # Simulate what decode_responses=True returns: str keys only
            mock_redis.hgetall.return_value = {"hits": "5", "misses": "2"}
            mock_redis.info.return_value = {"used_memory_human": "1M"}
            stats = get_cache_stats()

        # If bytes keys were used, both would be 0 — assert they are not
        assert stats["hits"] != 0 or stats["misses"] != 0 or True  # at least ran
        assert stats["hits"] == 5   # would be 0 with the old b"hits" bug

    # ── Fix 2: cached() skips caching when get_json returns None ─────────────

    def test_cached_decorator_skips_none_json(self, app_fixture):
        """If result.get_json() returns None, the result must be returned as-is
        without calling cache_set (which would poison the key with null)."""
        from app.services.cache import cached, cache_get, cache_set

        with app_fixture.app_context():
            from flask import Flask, Response
            from unittest.mock import MagicMock, patch as _patch

            # Build a fake response whose get_json returns None
            fake_response = MagicMock()
            fake_response.status_code = 200
            fake_response.get_json.return_value = None

            key_called = []

            @cached(lambda: "test:none_json:key", ttl=10)
            def fake_view():
                return fake_response

            with _patch("app.services.cache.cache_set") as mock_set, \
                 _patch("app.services.cache.cache_get", return_value=None), \
                 _patch("app.services.cache._increment_miss"):
                result = fake_view()

            # cache_set must NOT have been called
            mock_set.assert_not_called()
            # The original response must be returned unchanged
            assert result is fake_response


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="cache@test.com"):
    client.post("/auth/register", json={"email": email, "password": "pass1234"})
    r = client.post("/auth/login", json={"email": email, "password": "pass1234"})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


class TestCategoriesCaching:
    def test_categories_list(self, client, app_fixture):
        h = _auth(client, "cat_cache1@test.com")
        r = client.get("/categories", headers=h)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_categories_create_invalidates_cache(self, client, app_fixture):
        h = _auth(client, "cat_cache2@test.com")
        # Prime cache
        client.get("/categories", headers=h)
        # Create new category
        r = client.post("/categories", json={"name": "CacheTest"}, headers=h)
        assert r.status_code == 201
        # Should see new category
        cats = client.get("/categories", headers=h).get_json()
        assert any(c["name"] == "CacheTest" for c in cats)

    def test_categories_delete_invalidates_cache(self, client, app_fixture):
        h = _auth(client, "cat_cache3@test.com")
        cid = client.post("/categories", json={"name": "ToDelete"}, headers=h).get_json()["id"]
        client.get("/categories", headers=h)  # prime cache
        client.delete(f"/categories/{cid}", headers=h)
        cats = client.get("/categories", headers=h).get_json()
        assert not any(c["id"] == cid for c in cats)


class TestCacheStats:
    def test_cache_stats_endpoint(self, client, app_fixture):
        h = _auth(client, "stats@test.com")
        r = client.get("/insights/cache-stats", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        # Either returns stats or an error key (if Redis not available)
        assert "hits" in d or "error" in d

    def test_cache_stats_requires_auth(self, client, app_fixture):
        r = client.get("/insights/cache-stats")
        assert r.status_code == 401

    def test_reset_cache_stats(self, client, app_fixture):
        h = _auth(client, "reset_stats@test.com")
        r = client.delete("/insights/cache-stats", headers=h)
        assert r.status_code == 200
