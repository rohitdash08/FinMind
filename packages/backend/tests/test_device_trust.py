"""Tests for device trust management (issue #125)."""
import json, pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_redis():
    store = {}
    r = MagicMock()
    def hset(key, field, val): store.setdefault(key, {})[field] = val
    def hget(key, field): v = store.get(key, {}).get(field); return v.encode() if isinstance(v,str) else v
    def hgetall(key): return {k: v.encode() if isinstance(v,str) else v for k,v in store.get(key,{}).items()}
    def expire(key, ttl): pass
    r.hset.side_effect = hset; r.hget.side_effect = hget
    r.hgetall.side_effect = hgetall; r.expire.side_effect = expire
    return r, store

def test_register_new_device(mock_redis):
    r, _ = mock_redis
    with patch("app.services.device_trust.redis_client", r):
        from app.services.device_trust import register_device
        d = register_device(1, "Mozilla/5.0 (Windows)", "192.168.1.1")
        assert d["trusted"] is True
        assert "fingerprint" in d

def test_is_trusted_after_register(mock_redis):
    r, _ = mock_redis
    with patch("app.services.device_trust.redis_client", r):
        from app.services.device_trust import register_device, is_trusted
        register_device(1, "Chrome/120", "10.0.0.1")
        assert is_trusted(1, "Chrome/120", "10.0.0.1") is True

def test_unknown_device_not_trusted(mock_redis):
    r, _ = mock_redis
    with patch("app.services.device_trust.redis_client", r):
        from app.services.device_trust import is_trusted
        assert is_trusted(1, "Safari/17", "203.0.113.1") is False

def test_revoke_device(mock_redis):
    r, _ = mock_redis
    with patch("app.services.device_trust.redis_client", r):
        from app.services.device_trust import register_device, revoke_device, is_trusted
        d = register_device(2, "Firefox/120", "172.16.0.1")
        revoke_device(2, d["fingerprint"])
        assert is_trusted(2, "Firefox/120", "172.16.0.1") is False

def test_auto_name_detection(mock_redis):
    r, _ = mock_redis
    with patch("app.services.device_trust.redis_client", r):
        from app.services.device_trust import register_device
        d = register_device(3, "Mozilla/5.0 (iPhone; CPU)", "1.2.3.4")
        assert d["name"] == "iPhone"
