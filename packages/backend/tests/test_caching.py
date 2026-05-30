from unittest.mock import patch


class _FakeRedis:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value

    def set(self, key, value, **kw):
        self._data[key] = value

    def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)

    def flushdb(self):
        self._data.clear()

    def scan(self, cursor=0, match=None, count=100):
        return (0, [])


def _patch_cache():
    fake = _FakeRedis()
    return patch("app.services.cache.redis_client", fake)


def test_cache_get_set():
    with _patch_cache():
        from app.services.cache import cache_get, cache_set, clear_stats, get_stats

        clear_stats()
        key = "test:key:1"
        value = {"hello": "world", "num": 42}

        assert cache_get(key) is None

        cache_set(key, value, ttl_seconds=60)
        result = cache_get(key)
        assert result == value

        stats = get_stats()
        assert stats["hits"] >= 1
        assert stats["sets"] >= 1


def test_cache_aside_pattern():
    with _patch_cache():
        from app.services.cache import (
            cache_aside,
            cache_delete,
            cache_get,
            clear_stats,
        )

        clear_stats()
        key = "test:aside:1"
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return {"data": "expensive", "call": call_count}

        result1 = cache_aside(key, fetch, ttl_seconds=30)
        assert result1["call"] == 1
        assert call_count == 1

        result2 = cache_aside(key, fetch, ttl_seconds=30)
        assert result2["call"] == 1
        assert call_count == 1

        cache_delete(key)
        result3 = cache_aside(key, fetch, ttl_seconds=30)
        assert result3["call"] == 2
        assert call_count == 2


def test_cache_hit_rate():
    with _patch_cache():
        from app.services.cache import cache_get, cache_set, get_stats, clear_stats

        clear_stats()
        assert get_stats()["hit_rate"] == 0.0

        cache_set("k1", "v1", 60)
        cache_get("k1")
        cache_get("k1")
        cache_get("missing")

        stats = get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] > 0


def test_cache_invalidation_on_expense_create(client, auth_header):
    from app.services.cache import cache_set, monthly_summary_key, get_stats, clear_stats

    clear_stats()
    cache_set(monthly_summary_key(1, "2026-05"), {"data": "old"}, ttl_seconds=60)

    r = client.post(
        "/expenses",
        json={"amount": 50, "description": "Test invalidation", "date": "2026-05-01"},
        headers=auth_header,
    )
    assert r.status_code == 201

    stats = get_stats()
    assert stats["invalidations"] >= 1


def test_cache_invalidation_on_bill_create(client, auth_header):
    from app.services.cache import (
        cache_set,
        upcoming_bills_key,
        get_stats,
        clear_stats,
    )

    clear_stats()
    cache_set(upcoming_bills_key(1), [{"id": 99}], ttl_seconds=60)

    r = client.post(
        "/bills",
        json={
            "name": "Test Cache Bill",
            "amount": 100,
            "next_due_date": "2026-06-15",
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    stats = get_stats()
    assert stats["invalidations"] >= 1


def test_cache_warming_endpoint(client, auth_header):
    r = client.post("/cache/warm", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "cache warmed"


def test_cache_warming_populates_keys(client, auth_header):
    from app.services.cache import cache_get, categories_key, dashboard_summary_key
    from datetime import date

    r = client.post("/cache/warm", headers=auth_header)
    assert r.status_code == 200

    uid = 1
    ym = date.today().strftime("%Y-%m")
    cats = cache_get(categories_key(uid))
    assert cats is not None
    assert isinstance(cats, list)

    dsh = cache_get(dashboard_summary_key(uid, ym))
    assert dsh is not None
    assert "summary" in dsh


def test_cache_stats_endpoint(client, auth_header):
    from app.services.cache import clear_stats

    clear_stats()

    r = client.get("/cache/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "hits" in data
    assert "misses" in data
    assert "hit_rate" in data
