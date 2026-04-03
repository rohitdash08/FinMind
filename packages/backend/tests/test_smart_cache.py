"""
Tests for smart caching strategy.
Issue #127: Verify multi-layer caching, tag-based invalidation, graceful degradation.
"""

import pytest
from unittest.mock import MagicMock, patch, call
import json


class TestCacheKeyHelpers:
    def test_monthly_summary_key_format(self):
        from packages.backend.app.services.cache import monthly_summary_key
        key = monthly_summary_key(42, "2026-04")
        assert key == "user:42:monthly_summary:2026-04"

    def test_categories_key_format(self):
        from packages.backend.app.services.cache import categories_key
        assert categories_key(1) == "user:1:categories"

    def test_upcoming_bills_key_format(self):
        from packages.backend.app.services.cache import upcoming_bills_key
        assert upcoming_bills_key(5) == "user:5:upcoming_bills"

    def test_insights_key_format(self):
        from packages.backend.app.services.cache import insights_key
        assert insights_key(3, "2026-03") == "insights:3:2026-03"

    def test_dashboard_summary_key_format(self):
        from packages.backend.app.services.cache import dashboard_summary_key
        assert dashboard_summary_key(7, "2026-04") == "user:7:dashboard_summary:2026-04"

    def test_user_tag_key_format(self):
        from packages.backend.app.services.cache import user_tag_key
        assert user_tag_key(10) == "user:10:cache_tags"


class TestCacheSetGet:
    def test_cache_set_with_ttl(self):
        mock_redis = MagicMock()
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_set
            result = cache_set("test:key", {"data": 42}, ttl_seconds=300)
            assert result is True
            mock_redis.setex.assert_called_once()

    def test_cache_set_without_ttl(self):
        mock_redis = MagicMock()
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_set
            result = cache_set("test:key", {"data": 42})
            assert result is True
            mock_redis.set.assert_called_once()

    def test_cache_set_registers_user_tag(self):
        mock_redis = MagicMock()
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_set
            cache_set("user:5:summary", {"x": 1}, ttl_seconds=60, user_id=5)
            mock_redis.sadd.assert_called_once_with("user:5:cache_tags", "user:5:summary")

    def test_cache_get_hit(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"value": 99}).encode()
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_get
            result = cache_get("some:key")
            assert result == {"value": 99}

    def test_cache_get_miss(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_get
            assert cache_get("missing:key") is None


class TestGracefulDegradation:
    def test_cache_get_returns_none_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection refused")
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_get
            result = cache_get("any:key")
            assert result is None

    def test_cache_set_returns_false_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Connection refused")
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_set
            result = cache_set("any:key", {"x": 1}, ttl_seconds=60)
            assert result is False

    def test_cache_operations_return_defaults_when_redis_unavailable(self):
        with patch("packages.backend.app.services.cache._redis", return_value=None):
            from packages.backend.app.services.cache import cache_get, cache_set, invalidate_user_cache
            assert cache_get("key") is None
            assert cache_set("key", "val") is False
            assert invalidate_user_cache(1) == 0


class TestTagBasedInvalidation:
    def test_invalidate_user_cache_uses_tag_keys(self):
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {
            b"user:1:monthly_summary:2026-04",
            b"user:1:categories",
            b"user:1:upcoming_bills",
        }
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [1, 1, 1, 1]
        mock_redis.pipeline.return_value = mock_pipe
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import invalidate_user_cache
            deleted = invalidate_user_cache(1)
            mock_redis.smembers.assert_called_once_with("user:1:cache_tags")
            assert mock_pipe.execute.called

    def test_invalidate_user_cache_fallback_to_pattern_when_no_tags(self):
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = set()
        mock_redis.scan.return_value = (0, [])
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import invalidate_user_cache
            invalidate_user_cache(7)
            # Should fall back to pattern scanning
            assert mock_redis.scan.called


class TestCacheAsidPattern:
    def test_cache_or_compute_returns_cached_value(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"cached": True}).encode()
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_or_compute
            compute_fn = MagicMock(return_value={"fresh": True})
            result = cache_or_compute("key", compute_fn, ttl_seconds=60)
            assert result == {"cached": True}
            compute_fn.assert_not_called()

    def test_cache_or_compute_calls_fn_on_miss(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("packages.backend.app.services.cache._redis", return_value=mock_redis):
            from packages.backend.app.services.cache import cache_or_compute
            compute_fn = MagicMock(return_value={"computed": True})
            result = cache_or_compute("key", compute_fn, ttl_seconds=60)
            assert result == {"computed": True}
            compute_fn.assert_called_once()


class TestTTLConstants:
    def test_ttl_values_are_reasonable(self):
        from packages.backend.app.services import cache
        assert cache.TTL_MONTHLY_SUMMARY >= 60
        assert cache.TTL_CATEGORIES >= 600
        assert cache.TTL_INSIGHTS >= 600
        assert cache.TTL_UPCOMING_BILLS >= 60
        assert cache.TTL_LONG > cache.TTL_SHORT