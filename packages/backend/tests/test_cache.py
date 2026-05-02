import json
from unittest.mock import patch, MagicMock

import pytest

from app.services.cache import (
    CacheManager,
    _calculate_hit_rate,
    cache_manager,
    dashboard_summary_key,
    monthly_summary_key,
    categories_key,
    insights_key,
    upcoming_bills_key,
)


# ---------------------------------------------------------------------------
# Pure-function / key tests (no Redis needed)
# ---------------------------------------------------------------------------

class TestCalculateHitRate:
    def test_returns_zero_when_no_traffic(self):
        assert _calculate_hit_rate({}) == 0.0

    def test_returns_full_hit_rate(self):
        info = {"keyspace_hits": 100, "keyspace_misses": 0}
        assert _calculate_hit_rate(info) == 1.0

    def test_returns_half_hit_rate(self):
        info = {"keyspace_hits": 50, "keyspace_misses": 50}
        assert _calculate_hit_rate(info) == 0.5

    def test_rounds_to_four_decimals(self):
        info = {"keyspace_hits": 1, "keyspace_misses": 2}
        result = _calculate_hit_rate(info)
        assert result == round(1 / 3, 4)


class TestKeyFunctions:
    def test_monthly_summary_key(self):
        assert monthly_summary_key(42, "2025-01") == "user:42:monthly_summary:2025-01"

    def test_categories_key(self):
        assert categories_key(7) == "user:7:categories"

    def test_upcoming_bills_key(self):
        assert upcoming_bills_key(3) == "user:3:upcoming_bills"

    def test_insights_key(self):
        assert insights_key(10, "2025-06") == "insights:10:2025-06"

    def test_dashboard_summary_key(self):
        assert dashboard_summary_key(1, "2025-03") == "user:1:dashboard_summary:2025-03"


class TestCacheManagerTTLStrategies:
    def test_all_strategies_defined(self):
        expected = {"realtime", "short", "medium", "long", "static"}
        assert set(CacheManager.TTL_STRATEGIES.keys()) == expected

    def test_ttl_values(self):
        assert CacheManager.TTL_STRATEGIES["realtime"] == 30
        assert CacheManager.TTL_STRATEGIES["short"] == 300
        assert CacheManager.TTL_STRATEGIES["medium"] == 1800
        assert CacheManager.TTL_STRATEGIES["long"] == 3600
        assert CacheManager.TTL_STRATEGIES["static"] == 86400


class TestCacheManagerSingleton:
    def test_is_cache_manager_instance(self):
        assert isinstance(cache_manager, CacheManager)


# ---------------------------------------------------------------------------
# Redis-mocked tests
# ---------------------------------------------------------------------------

class TestCacheManagerGetOrSet:
    @patch("app.services.cache.cache_get")
    @patch("app.services.cache.cache_set")
    def test_returns_computed_value_on_miss(self, mock_set, mock_get):
        mock_get.return_value = None
        cm = CacheManager()
        result = cm.get_or_set("k", lambda: {"hello": "world"}, ttl_strategy="short")
        assert result == {"hello": "world"}
        mock_set.assert_called_once_with("k", {"hello": "world"}, 300)

    @patch("app.services.cache.cache_get")
    @patch("app.services.cache.cache_set")
    def test_returns_cached_value_on_hit(self, mock_set, mock_get):
        mock_get.return_value = {"cached": True}
        cm = CacheManager()
        call_count = {"n": 0}

        def factory():
            call_count["n"] += 1
            return {"fresh": True}

        result = cm.get_or_set("k", factory, ttl_strategy="short")
        assert result == {"cached": True}
        assert call_count["n"] == 0
        mock_set.assert_not_called()

    @patch("app.services.cache.cache_get")
    @patch("app.services.cache.cache_set")
    def test_different_keys_independent(self, mock_set, mock_get):
        mock_get.return_value = None
        cm = CacheManager()
        a = cm.get_or_set("a", lambda: "A", ttl_strategy="short")
        b = cm.get_or_set("b", lambda: "B", ttl_strategy="short")
        assert a == "A"
        assert b == "B"

    @patch("app.services.cache.cache_get")
    @patch("app.services.cache.cache_set")
    def test_factory_returning_none_is_not_cached(self, mock_set, mock_get):
        """cache_get returns None for None-valued keys (json.loads of 'null'
        returns None), so the factory is called again on the second pass."""
        mock_get.return_value = None
        cm = CacheManager()
        call_count = {"n": 0}

        def factory():
            call_count["n"] += 1
            return None

        cm.get_or_set("k", factory)
        cm.get_or_set("k", factory)
        assert call_count["n"] == 2

    @patch("app.services.cache.cache_get")
    def test_factory_exception_propagates(self, mock_get):
        mock_get.return_value = None
        cm = CacheManager()
        with pytest.raises(ValueError, match="boom"):
            cm.get_or_set("k", lambda: (_ for _ in ()).throw(ValueError("boom")))

    @patch("app.services.cache.cache_get")
    @patch("app.services.cache.cache_set")
    def test_unknown_strategy_defaults_to_medium(self, mock_set, mock_get):
        mock_get.return_value = None
        cm = CacheManager()
        result = cm.get_or_set("k", lambda: "val", ttl_strategy="bogus")
        assert result == "val"
        mock_set.assert_called_once_with("k", "val", 1800)

    @patch("app.services.cache.cache_get", side_effect=Exception("redis down"))
    @patch("app.services.cache.cache_set")
    def test_redis_get_error_falls_through_to_factory(self, mock_set, mock_get):
        cm = CacheManager()
        result = cm.get_or_set("k", lambda: "fallback")
        assert result == "fallback"

    @patch("app.services.cache.cache_get")
    @patch("app.services.cache.cache_set", side_effect=Exception("redis down"))
    def test_redis_set_error_still_returns_value(self, mock_set, mock_get):
        mock_get.return_value = None
        cm = CacheManager()
        result = cm.get_or_set("k", lambda: "val")
        assert result == "val"


class TestCacheManagerInvalidation:
    @patch("app.services.cache.cache_delete_patterns")
    def test_invalidate_user_calls_correct_pattern(self, mock_del):
        cm = CacheManager()
        cm.invalidate_user(99)
        mock_del.assert_called_once_with(["user:99:*"])

    @patch("app.services.cache.cache_delete_patterns")
    def test_invalidate_user_type_calls_correct_pattern(self, mock_del):
        cm = CacheManager()
        cm.invalidate_user_type(50, "dashboard_summary")
        mock_del.assert_called_once_with(["user:50:dashboard_summary:*"])

    @patch("app.services.cache.cache_delete_patterns", side_effect=Exception("fail"))
    def test_invalidate_user_handles_redis_error(self, mock_del):
        cm = CacheManager()
        cm.invalidate_user(1)  # should not raise

    @patch("app.services.cache.cache_delete_patterns", side_effect=Exception("fail"))
    def test_invalidate_user_type_handles_redis_error(self, mock_del):
        cm = CacheManager()
        cm.invalidate_user_type(1, "dashboard_summary")  # should not raise


class TestCacheManagerStats:
    @patch("app.services.cache.redis_client")
    def test_get_stats_returns_expected_keys(self, mock_redis):
        mock_redis.info.side_effect = [
            {"keyspace_hits": 100, "keyspace_misses": 25},
            {"used_memory_human": "1.5M"},
        ]
        mock_redis.dbsize.return_value = 42
        cm = CacheManager()
        stats = cm.get_stats()
        assert stats["hits"] == 100
        assert stats["misses"] == 25
        assert stats["hit_rate"] == 0.8
        assert stats["memory_used"] == "1.5M"
        assert stats["keys"] == 42

    @patch("app.services.cache.redis_client")
    def test_get_stats_returns_error_on_failure(self, mock_redis):
        mock_redis.info.side_effect = Exception("connection refused")
        cm = CacheManager()
        stats = cm.get_stats()
        assert stats.get("error") == "stats_unavailable"
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["keys"] == 0


class TestBackwardCompatibility:
    @patch("app.services.cache.redis_client")
    def test_cache_set_with_ttl(self, mock_redis):
        from app.services.cache import cache_set
        cache_set("k", {"a": 1}, 60)
        mock_redis.setex.assert_called_once_with("k", 60, json.dumps({"a": 1}))

    @patch("app.services.cache.redis_client")
    def test_cache_set_without_ttl(self, mock_redis):
        from app.services.cache import cache_set
        cache_set("k", {"a": 1}, None)
        mock_redis.set.assert_called_once_with("k", json.dumps({"a": 1}))

    @patch("app.services.cache.redis_client")
    def test_cache_get_returns_data(self, mock_redis):
        from app.services.cache import cache_get
        mock_redis.get.return_value = json.dumps({"a": 1})
        assert cache_get("k") == {"a": 1}

    @patch("app.services.cache.redis_client")
    def test_cache_get_returns_none_for_missing(self, mock_redis):
        from app.services.cache import cache_get
        mock_redis.get.return_value = None
        assert cache_get("missing") is None

    @patch("app.services.cache.redis_client")
    def test_cache_delete_patterns_scans_and_deletes(self, mock_redis):
        from app.services.cache import cache_delete_patterns
        mock_redis.scan.side_effect = [
            (5, ["key1", "key2"]),
            (0, ["key3"]),
        ]
        cache_delete_patterns(["test:*"])
        assert mock_redis.delete.call_count == 2


class TestCacheStatsEndpoint:
    def test_cache_stats_requires_auth(self, client):
        r = client.get("/dashboard/cache-stats")
        assert r.status_code == 401

    @patch("app.services.cache.redis_client")
    def test_cache_stats_returns_json(self, mock_redis, app_fixture):
        mock_redis.info.side_effect = [
            {"keyspace_hits": 10, "keyspace_misses": 2},
            {"used_memory_human": "500K"},
        ]
        mock_redis.dbsize.return_value = 5
        # Create a valid JWT token directly to avoid needing Redis in auth flow
        from flask_jwt_extended import create_access_token
        with app_fixture.app_context():
            token = create_access_token(identity="1")
        client = app_fixture.test_client()
        r = client.get(
            "/dashboard/cache-stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert "hits" in data
        assert "misses" in data
        assert "hit_rate" in data
        assert "memory_used" in data
        assert "keys" in data
