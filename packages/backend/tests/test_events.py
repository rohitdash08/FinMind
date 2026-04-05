"""Tests for event-driven system (issue #97)."""
import json
from unittest.mock import MagicMock, patch

def _mock_redis():
    store, lists = {}, {}
    r = MagicMock()
    def rpush(k,v): lists.setdefault(k,[]).append(v)
    def lrange(k,s,e): items=lists.get(k,[]); return (items[s:] if e==-1 else items[s:e+1])
    def llen(k): return len(lists.get(k,[]))
    def expire(k,t): pass
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    def setex(k,t,v): store[k]=v
    r.rpush.side_effect=rpush; r.lrange.side_effect=lrange; r.llen.side_effect=llen
    r.expire.side_effect=expire; r.get.side_effect=get; r.setex.side_effect=setex
    return r

def test_emit_and_get():
    r = _mock_redis()
    with patch("app.services.events.redis_client", r):
        from app.services.events import emit, get_events
        emit("expense.created", 1, {"amount": 50})
        events = get_events(1)
        assert len(events) == 1
        assert events[0]["type"] == "expense.created"

def test_unknown_event_raises():
    r = _mock_redis()
    with patch("app.services.events.redis_client", r):
        from app.services.events import emit
        import pytest
        with pytest.raises(ValueError):
            emit("unknown.event", 1, {})

def test_filter_by_type():
    r = _mock_redis()
    with patch("app.services.events.redis_client", r):
        from app.services.events import emit, get_events
        emit("expense.created", 1, {})
        emit("bill.due_soon", 1, {})
        events = get_events(1, event_type="bill.due_soon")
        assert all(e["type"] == "bill.due_soon" for e in events)
