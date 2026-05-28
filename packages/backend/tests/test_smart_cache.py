"""
Tests for smart caching service.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from app.services.smart_cache import SmartCache, cache, TTL_PRESETS


class TestSmartCache:
    def test_set_and_get(self):
        c = SmartCache(redis=MagicMock())
        # Mock redis get/set
        c.redis.get.return_value = json.dumps({"amount": 100})
        c.redis.pipeline.return_value.execute.return_value = [True]
        c.redis.pipeline.return_value.setex.return_value = True
        c.redis.pipeline.return_value.hincrby.return_value = True
        c.redis.pipeline.return_value.expire.return_value = True

        c.set("test", "key1", {"amount": 100}, ttl="standard")
        result = c.get("test", "key1")
        assert result == {"amount": 100}

    def test_miss_returns_none(self):
        c = SmartCache(redis=MagicMock())
        c.redis.get.return_value = None
        c.redis.pipeline.return_value.hincrby.return_value = True
        c.redis.pipeline.return_value.expire.return_value = True
        c.redis.pipeline.return_value.execute.return_value = []

        result = c.get("test", "nonexistent")
        assert result is None

    def test_get_or_set_calls_factory_on_miss(self):
        c = SmartCache(redis=MagicMock())
        c.redis.get.return_value = None  # Cache miss
        c.redis.pipeline.return_value.setex.return_value = True
        c.redis.pipeline.return_value.execute.return_value = []
        c.redis.pipeline.return_value.hincrby.return_value = True
        c.redis.pipeline.return_value.expire.return_value = True

        factory_called = False
        def factory():
            nonlocal factory_called
            factory_called = True
            return "computed_value"

        result = c.get_or_set("test", "key1", factory, ttl="standard")
        assert factory_called is True
        assert result == "computed_value"

    def test_get_or_set_returns_cached(self):
        c = SmartCache(redis=MagicMock())
        c.redis.get.return_value = json.dumps("cached_value")
        c.redis.pipeline.return_value.hincrby.return_value = True
        c.redis.pipeline.return_value.expire.return_value = True
        c.redis.pipeline.return_value.execute.return_value = []

        factory_called = False
        def factory():
            nonlocal factory_called
            factory_called = True

        result = c.get_or_set("test", "key1", factory, ttl="standard")
        assert factory_called is False
        assert result == "cached_value"

    def test_invalidate_tag(self):
        c = SmartCache(redis=MagicMock())
        c.redis.smembers.return_value = {b"key1", b"key2"}
        c.redis.delete.return_value = 2

        count = c.invalidate_tag("expenses")
        assert count == 2

    def test_invalidate_empty_tag(self):
        c = SmartCache(redis=MagicMock())
        c.redis.smembers.return_value = set()

        count = c.invalidate_tag("nonexistent")
        assert count == 0

    def test_ttl_presets(self):
        assert TTL_PRESETS["realtime"] == 30
        assert TTL_PRESETS["daily"] == 86400
        assert TTL_PRESETS["standard"] == 900

    def test_metrics(self):
        c = SmartCache(redis=MagicMock())
        c.redis.hgetall.return_value = {b"hits": 80, b"misses": 20}

        metrics = c.get_metrics("test")
        assert metrics["hits"] == 80
        assert metrics["misses"] == 20
        assert metrics["hit_rate"] == 0.8
