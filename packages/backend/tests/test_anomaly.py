"""Tests for login anomaly detection (issue #124)."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_redis():
    store = {}
    sets = {}
    r = MagicMock()

    def incr(key):
        store[key] = store.get(key, 0) + 1
        return store[key]

    def get(key):
        v = store.get(key)
        return str(v).encode() if v is not None else None

    def delete(*keys):
        for k in keys:
            store.pop(k, None)

    def expire(key, ttl):
        pass

    def setex(key, ttl, val):
        store[key] = val

    def sadd(key, member):
        sets.setdefault(key, set()).add(member)

    def sismember(key, member):
        return member in sets.get(key, set())

    r.incr.side_effect = incr
    r.get.side_effect = get
    r.delete.side_effect = delete
    r.expire.side_effect = expire
    r.setex.side_effect = setex
    r.sadd.side_effect = sadd
    r.sismember.side_effect = sismember
    return r, store, sets


def test_brute_force_not_triggered_below_limit(mock_redis):
    r, store, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import record_failed_login, is_brute_forced
        for _ in range(4):
            record_failed_login("test@example.com")
        assert not is_brute_forced("test@example.com")


def test_brute_force_triggered_at_limit(mock_redis):
    r, store, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import record_failed_login, is_brute_forced
        for _ in range(5):
            record_failed_login("test@example.com")
        assert is_brute_forced("test@example.com")


def test_clear_failed_logins(mock_redis):
    r, store, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import record_failed_login, clear_failed_logins, is_brute_forced
        for _ in range(5):
            record_failed_login("test@example.com")
        clear_failed_logins("test@example.com")
        assert not is_brute_forced("test@example.com")


def test_new_device_first_login(mock_redis):
    r, _, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import is_new_device
        assert is_new_device(1, "Mozilla/5.0", "192.168.1.1") is True


def test_same_device_not_flagged(mock_redis):
    r, _, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import is_new_device
        is_new_device(2, "Mozilla/5.0", "10.0.0.1")  # register
        assert is_new_device(2, "Mozilla/5.0", "10.0.0.1") is False  # same device


def test_check_login_anomalies_new_device_alert(mock_redis):
    r, _, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import check_login_anomalies
        alerts = check_login_anomalies(99, "user@test.com", "Chrome/120", "203.0.113.1")
        assert any(a["type"] == "new_device" for a in alerts)
        assert alerts[0]["severity"] == "medium"


def test_check_login_anomalies_known_device_no_alert(mock_redis):
    r, _, _ = mock_redis
    with patch("app.services.anomaly.redis_client", r):
        from app.services.anomaly import check_login_anomalies, is_new_device
        # Pre-register device
        is_new_device(50, "Safari/17", "172.16.0.1")
        alerts = check_login_anomalies(50, "user2@test.com", "Safari/17", "172.16.0.1")
        assert not any(a["type"] == "new_device" for a in alerts)
