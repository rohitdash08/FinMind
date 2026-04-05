"""Tests for smart caching strategy (issue #127)."""
import json
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_redis():
    store = {}
    sets = {}
    r = MagicMock()

    def setex(key, ttl, val):
        store[key] = val

    def get(key):
        return store.get(key)

    def delete(*keys):
        for k in keys:
            store.pop(k, None)
            sets.pop(k, None)

    def sadd(key, member):
        sets.setdefault(key, set()).add(member)

    def smembers(key):
        return sets.get(key, set())

    r.setex.side_effect = setex
    r.get.side_effect = get
    r.delete.side_effect = delete
    r.sadd.side_effect = sadd
    r.smembers.side_effect = smembers
    return r, store, sets


def test_smart_set_and_get(mock_redis):
    r, store, _ = mock_redis
    with patch("app.services.smart_cache.redis_client", r):
        from app.services.smart_cache import smart_set, smart_get
        smart_set("test:key", {"val": 42}, ttl_seconds=300)
        result = smart_get("test:key")
        assert result == {"val": 42}


def test_cache_miss_returns_none(mock_redis):
    r, _, _ = mock_redis
    with patch("app.services.smart_cache.redis_client", r):
        from app.services.smart_cache import smart_get
        assert smart_get("nonexistent:key") is None


def test_smart_get_or_compute_computes_on_miss(mock_redis):
    r, store, _ = mock_redis
    with patch("app.services.smart_cache.redis_client", r):
        from app.services.smart_cache import smart_get_or_compute
        called = []

        def compute():
            called.append(1)
            return {"computed": True}

        result = smart_get_or_compute("comp:key", compute, ttl_seconds=60)
        assert result == {"computed": True}
        assert len(called) == 1


def test_smart_get_or_compute_hits_cache(mock_redis):
    r, store, _ = mock_redis
    store["hit:key"] = json.dumps({"cached": True})
    with patch("app.services.smart_cache.redis_client", r):
        from app.services.smart_cache import smart_get_or_compute
        called = []

        def compute():
            called.append(1)
            return {}

        result = smart_get_or_compute("hit:key", compute, ttl_seconds=60)
        assert result == {"cached": True}
        assert len(called) == 0  # compute not called


def test_invalidate_user_clears_all_keys(mock_redis):
    r, store, sets = mock_redis
    store["user:1:summary"] = json.dumps({"x": 1})
    store["user:1:dashboard"] = json.dumps({"y": 2})
    sets["cache:tags:user:1"] = {"user:1:summary", "user:1:dashboard"}
    with patch("app.services.smart_cache.redis_client", r):
        from app.services.smart_cache import invalidate_user
        invalidate_user(1)
        assert "user:1:summary" not in store
        assert "user:1:dashboard" not in store


def test_ttl_constants():
    from app.services.smart_cache import TTL_REALTIME, TTL_SUMMARY, TTL_ANALYTICS, TTL_STATIC
    assert TTL_REALTIME < TTL_SUMMARY < TTL_ANALYTICS < TTL_STATIC
