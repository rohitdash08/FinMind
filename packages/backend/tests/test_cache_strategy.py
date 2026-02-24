"""Tests for smart caching strategy (issue #127).

These tests use fakeredis so no real Redis instance is needed.
"""
import pytest
import fakeredis
from unittest.mock import patch

import app.extensions as _ext
import app.services.cache as _cache_mod
import app.routes.auth as _auth_mod

from app.services.cache import (
    TTL_SHORT, TTL_STANDARD, TTL_MEDIUM, TTL_LONG, TTL_DIGEST,
    monthly_summary_key, dashboard_summary_key, categories_key,
    upcoming_bills_key, insights_key, digest_key, inflation_key,
    savings_key, breakdown_key, notifications_key, metrics_key,
    cache_set, cache_get, cache_delete, cache_delete_patterns,
    invalidate_user_caches, cache_stats,
)


@pytest.fixture(autouse=True)
def fake_redis_patch():
    """Replace the global redis_client with fakeredis across all modules."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    with patch.object(_ext, "redis_client", fake), \
         patch.object(_cache_mod, "redis_client", fake), \
         patch.object(_auth_mod, "redis_client", fake):
        yield fake
    fake.flushall()


# ── TTL constants ─────────────────────────────────────────────────────────────

class TestTTLConstants:
    def test_ttl_values_are_positive(self):
        for ttl in [TTL_SHORT, TTL_STANDARD, TTL_MEDIUM, TTL_LONG, TTL_DIGEST]:
            assert ttl > 0

    def test_ttl_hierarchy(self):
        assert TTL_SHORT < TTL_STANDARD <= TTL_MEDIUM <= TTL_LONG

    def test_standard_is_300(self):
        assert TTL_STANDARD == 300

    def test_medium_is_600(self):
        assert TTL_MEDIUM == 600

    def test_short_is_60(self):
        assert TTL_SHORT == 60

    def test_long_is_1800(self):
        assert TTL_LONG == 1800


# ── Key builders ──────────────────────────────────────────────────────────────

class TestKeyBuilders:
    def test_monthly_summary_key(self):
        key = monthly_summary_key(1, "2026-02")
        assert "1" in key and "2026-02" in key

    def test_dashboard_key(self):
        key = dashboard_summary_key(42, "2026-01")
        assert "42" in key and "2026-01" in key

    def test_digest_key_includes_currency(self):
        key = digest_key(1, "2026-W08", "EUR")
        assert "EUR" in key

    def test_inflation_key_includes_months(self):
        key = inflation_key(1, 6)
        assert "6" in key

    def test_breakdown_key(self):
        key = breakdown_key(1, "2026-02")
        assert "2026-02" in key

    def test_savings_key(self):
        key = savings_key(1, 12)
        assert "12" in key

    def test_notifications_key(self):
        key = notifications_key(7)
        assert "7" in key

    def test_metrics_key(self):
        key = metrics_key(1, 30)
        assert "30" in key

    def test_all_keys_include_user_id(self):
        uid = 99
        keys = [
            monthly_summary_key(uid, "2026-02"),
            dashboard_summary_key(uid, "2026-02"),
            categories_key(uid),
            upcoming_bills_key(uid),
            insights_key(uid, "2026-02"),
            digest_key(uid, "W08", "INR"),
            inflation_key(uid, 3),
            savings_key(uid, 3),
            breakdown_key(uid, "2026-02"),
            notifications_key(uid),
            metrics_key(uid, 30),
        ]
        for k in keys:
            assert str(uid) in k, f"user_id not in key: {k}"

    def test_different_users_different_keys(self):
        assert monthly_summary_key(1, "2026-02") != monthly_summary_key(2, "2026-02")

    def test_insights_key_namespace(self):
        key = insights_key(1, "2026-02")
        assert key.startswith("insights:")


# ── Cache operations ─────────────────────────────────────────────────────────

class TestCacheOperations:
    def test_set_and_get(self):
        cache_set("test:key:1", {"value": 42}, ttl_seconds=60)
        result = cache_get("test:key:1")
        assert result == {"value": 42}

    def test_get_missing_returns_none(self):
        result = cache_get("test:nonexistent:xyz")
        assert result is None

    def test_set_string_value(self):
        cache_set("test:str:1", "hello", ttl_seconds=60)
        assert cache_get("test:str:1") == "hello"

    def test_set_list_value(self):
        cache_set("test:list:1", [1, 2, 3], ttl_seconds=60)
        assert cache_get("test:list:1") == [1, 2, 3]

    def test_delete_removes_key(self):
        cache_set("test:del:1", "hello", ttl_seconds=60)
        cache_delete("test:del:1")
        assert cache_get("test:del:1") is None

    def test_delete_patterns(self):
        cache_set("user:10:monthly_summary:2026-01", {"x": 1}, 60)
        cache_set("user:10:monthly_summary:2026-02", {"x": 2}, 60)
        count = cache_delete_patterns(["user:10:monthly_summary:*"])
        assert count == 2
        assert cache_get("user:10:monthly_summary:2026-01") is None
        assert cache_get("user:10:monthly_summary:2026-02") is None

    def test_invalidate_user_caches(self):
        # Set some user-specific keys
        cache_set("user:5:dashboard_summary:2026-02", {"x": 1}, 60)
        cache_set("user:5:savings:3", {"y": 2}, 60)
        cache_set("insights:5:2026-02", {"z": 3}, 60)
        # Verify they exist
        assert cache_get("user:5:dashboard_summary:2026-02") is not None
        assert cache_get("user:5:savings:3") is not None
        assert cache_get("insights:5:2026-02") is not None
        # Invalidate
        deleted = invalidate_user_caches(5)
        # All gone
        assert cache_get("user:5:dashboard_summary:2026-02") is None
        assert cache_get("user:5:savings:3") is None
        assert cache_get("insights:5:2026-02") is None
        assert deleted >= 3

    def test_invalidate_only_targets_user(self):
        """Invalidating user 5 should not remove user 6 keys."""
        cache_set("user:5:savings:3", {"y": 2}, 60)
        cache_set("user:6:savings:3", {"y": 9}, 60)
        invalidate_user_caches(5)
        assert cache_get("user:6:savings:3") == {"y": 9}

    def test_cache_stats_returns_dict(self):
        stats = cache_stats()
        assert isinstance(stats, dict)
        for key in ["total_requests", "hits", "misses", "hit_rate"]:
            assert key in stats

    def test_hit_rate_between_0_and_1(self):
        stats = cache_stats()
        assert 0.0 <= stats["hit_rate"] <= 1.0

    def test_cache_stats_tracks_hits(self):
        cache_set("test:stats:1", "v", 60)
        cache_get("test:stats:1")   # hit
        cache_get("test:stats:999")  # miss
        stats = cache_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

    def test_cache_stats_with_uid(self):
        cache_set("user:77:dashboard_summary:2026-02", {"x": 1}, 60)
        stats = cache_stats(uid=77)
        assert "user_active_keys" in stats
        assert stats["user_active_keys"] >= 1

    def test_cache_stats_hit_rate_after_hits(self):
        cache_set("test:hr:1", "v", 60)
        # 2 hits, 0 misses added
        cache_get("test:hr:1")
        cache_get("test:hr:1")
        stats = cache_stats()
        # hit_rate should be a valid float
        assert isinstance(stats["hit_rate"], float)


# ── API endpoints (using app_fixture from conftest) ───────────────────────────

class TestCacheEndpoints:
    def test_stats_requires_auth(self, client):
        resp = client.get("/cache/stats")
        assert resp.status_code in (401, 422)

    def test_stats_endpoint_exists(self, client):
        resp = client.get("/cache/stats")
        assert resp.status_code != 404

    def test_bust_requires_auth(self, client):
        resp = client.post("/cache/bust")
        assert resp.status_code in (401, 422)

    def test_bust_endpoint_exists(self, client):
        resp = client.post("/cache/bust")
        assert resp.status_code != 404

    def test_stats_with_auth(self, client, auth_header):
        resp = client.get("/cache/stats", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hits" in data
        assert "misses" in data
        assert "hit_rate" in data
        assert "total_requests" in data

    def test_stats_with_user_param(self, client, auth_header):
        resp = client.get("/cache/stats?user=true", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user_active_keys" in data

    def test_bust_with_auth(self, client, auth_header):
        resp = client.post("/cache/bust", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data
        assert "keys_deleted" in data
        assert data["message"] == "Cache cleared."
