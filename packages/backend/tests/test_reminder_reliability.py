"""Tests for reminder reliability tracking (issue #123)."""
import json, pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_redis():
    store, hashes = {}, {}
    r = MagicMock()
    def setex(k, t, v): store[k] = v
    def get(k): v = store.get(k); return v.encode() if isinstance(v,str) else v
    def hincrby(k, f, n): hashes.setdefault(k, {})[f] = hashes.get(k, {}).get(f, 0) + n
    def hgetall(k): return {f: str(v).encode() for f,v in hashes.get(k,{}).items()}
    r.setex.side_effect=setex; r.get.side_effect=get
    r.hincrby.side_effect=hincrby; r.hgetall.side_effect=hgetall
    return r, store, hashes

def test_record_and_get_status(mock_redis):
    r,_,_ = mock_redis
    with patch("app.services.reminder_reliability.redis_client", r):
        from app.services.reminder_reliability import record_sent, get_status
        record_sent(1, "email", 42)
        s = get_status(1)
        assert s["status"] == "sent"
        assert s["channel"] == "email"

def test_delivery_flow(mock_redis):
    r,_,_ = mock_redis
    with patch("app.services.reminder_reliability.redis_client", r):
        from app.services.reminder_reliability import record_sent, record_delivered, record_acknowledged, get_status
        record_sent(2, "push", 1); record_delivered(2); record_acknowledged(2)
        assert get_status(2)["status"] == "acknowledged"

def test_metrics_rates(mock_redis):
    r,_,_ = mock_redis
    with patch("app.services.reminder_reliability.redis_client", r):
        from app.services.reminder_reliability import record_sent, record_delivered, get_metrics
        record_sent(3, "sms", 1); record_sent(4, "sms", 1)
        record_delivered(3)
        m = get_metrics()
        assert m["total_sent"] == 2
        assert m["delivery_rate_pct"] == 50.0

def test_metrics_empty(mock_redis):
    r,_,_ = mock_redis
    with patch("app.services.reminder_reliability.redis_client", r):
        from app.services.reminder_reliability import get_metrics
        m = get_metrics()
        assert m["delivery_rate_pct"] == 0
