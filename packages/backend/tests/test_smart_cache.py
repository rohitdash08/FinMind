"""Tests for the smart caching strategy."""

import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.smart_cache import (
    _cache_key,
    invalidate_entity,
    get_cache_stats,
    clear_user_cache,
    CACHE_TTL,
    INVALIDATION_DEPS,
)


class TestCacheKeyGeneration:
    def test_basic_key(self):
        key = _cache_key("dashboard", 42)
        assert key == "smart:dashboard:42"

    def test_key_with_suffix(self):
        key = _cache_key("expenses", 42, "abc123")
        assert key == "smart:expenses:42:abc123"

    def test_different_entities_different_keys(self):
        k1 = _cache_key("dashboard", 1)
        k2 = _cache_key("expenses", 1)
        assert k1 != k2

    def test_different_users_different_keys(self):
        k1 = _cache_key("dashboard", 1)
        k2 = _cache_key("dashboard", 2)
        assert k1 != k2


class TestCacheTTLPolicies:
    def test_all_entities_have_ttl(self):
        expected = ["dashboard", "expenses", "categories", "bills", "insights", "analytics", "reminders"]
        for entity in expected:
            assert entity in CACHE_TTL, f"Missing TTL for {entity}"

    def test_ttl_values_positive(self):
        for entity, ttl in CACHE_TTL.items():
            assert ttl > 0, f"TTL for {entity} must be positive"

    def test_frequently_accessed_shorter_ttl(self):
        assert CACHE_TTL["expenses"] <= CACHE_TTL["categories"]
        assert CACHE_TTL["dashboard"] <= CACHE_TTL["categories"]


class TestInvalidationDeps:
    def test_expenses_invalidates_dashboard(self):
        assert "dashboard" in INVALIDATION_DEPS["expenses"]

    def test_expenses_invalidates_insights(self):
        assert "insights" in INVALIDATION_DEPS["expenses"]

    def test_categories_invalidates_dashboard(self):
        assert "dashboard" in INVALIDATION_DEPS["categories"]

    def test_bills_invalidates_dashboard(self):
        assert "dashboard" in INVALIDATION_DEPS["bills"]

    def test_reminders_no_deps(self):
        assert INVALIDATION_DEPS["reminders"] == []


class TestInvalidateEntity:
    @patch("app.services.smart_cache.redis_client")
    def test_invalidates_entity_and_deps(self, mock_redis):
        mock_redis.scan.return_value = (0, [])
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        invalidate_entity("expenses", 42)

        # Should scan for: expenses, dashboard, insights, analytics
        scan_calls = mock_redis.scan.call_args_list
        scanned_patterns = [c.kwargs.get("match", c.args[1] if len(c.args) > 1 else None) for c in scan_calls]

        # Filter None values from kwargs matching
        entity_patterns = []
        for call in scan_calls:
            _, kwargs = call
            if "match" in kwargs:
                entity_patterns.append(kwargs["match"])

        expected_entities = ["expenses", "dashboard", "insights", "analytics"]
        for entity in expected_entities:
            assert any(entity in p for p in entity_patterns), f"Missing invalidation for {entity}"

    @patch("app.services.smart_cache.redis_client")
    def test_invalidate_reminders_only_self(self, mock_redis):
        mock_redis.scan.return_value = (0, [])
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        invalidate_entity("reminders", 42)

        scan_calls = mock_redis.scan.call_args_list
        # Only reminders pattern scanned (no deps)
        entity_patterns = []
        for call in scan_calls:
            _, kwargs = call
            if "match" in kwargs:
                entity_patterns.append(kwargs["match"])
        assert len(entity_patterns) == 1
        assert "reminders" in entity_patterns[0]


class TestClearUserCache:
    @patch("app.services.smart_cache.redis_client")
    def test_clears_all_user_keys(self, mock_redis):
        mock_redis.scan.return_value = (0, ["smart:dashboard:42:abc", "smart:expenses:42:def"])
        clear_user_cache(42)
        mock_redis.delete.assert_called_once_with("smart:dashboard:42:abc", "smart:expenses:42:def")


class TestGetCacheStats:
    @patch("app.services.smart_cache.redis_client")
    def test_returns_stats_with_hit_rate(self, mock_redis):
        def fake_scan(cursor, match, count):
            if "hit" in match:
                return (0, ["cache:stats:hit:dashboard"])
            elif "miss" in match:
                return (0, ["cache:stats:miss:dashboard"])
            return (0, [])

        mock_redis.scan.side_effect = fake_scan
        mock_redis.get.side_effect = lambda k: "80" if "hit" in k else "20"

        stats = get_cache_stats()
        assert "dashboard" in stats
        assert stats["dashboard"]["hits"] == 80
        assert stats["dashboard"]["misses"] == 20
        assert stats["dashboard"]["hit_rate"] == 80.0
