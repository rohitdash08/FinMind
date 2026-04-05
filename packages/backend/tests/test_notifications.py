"""Tests for notification priority & grouping (issue #122)."""
import json, pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_redis():
    store, zsets, lists = {}, {}, {}
    r = MagicMock()
    def zadd(k, mapping):
        for v, s in mapping.items(): zsets.setdefault(k,[]).append((s,v))
        zsets[k].sort(reverse=True)
    def zrevrange(k, s, e):
        items = [v for _,v in zsets.get(k,[])]
        return items[s:e+1] if e >= 0 else items[s:]
    def zcard(k): return len(zsets.get(k,[]))
    def rpush(k,v): lists.setdefault(k,[]).append(v)
    def lrange(k,s,e): items=lists.get(k,[]); return items[s:e+1] if e>=0 else items[s:]
    def delete(k): lists.pop(k,None); zsets.pop(k,None)
    def get(k): return store.get(k)
    def setex(k,t,v): store[k]=v
    def expire(k,t): pass
    r.zadd.side_effect=zadd; r.zrevrange.side_effect=zrevrange; r.zcard.side_effect=zcard
    r.rpush.side_effect=rpush; r.lrange.side_effect=lrange; r.delete.side_effect=delete
    r.get.side_effect=get; r.setex.side_effect=setex; r.expire.side_effect=expire
    return r

def test_push_and_get(mock_redis):
    with patch("app.services.notifications.redis_client", mock_redis):
        from app.services.notifications import push, get_notifications, Priority
        push(1, "Bill due", "Pay rent", Priority.HIGH)
        notifs = get_notifications(1)
        assert len(notifs) == 1
        assert notifs[0]["title"] == "Bill due"

def test_priority_ordering(mock_redis):
    with patch("app.services.notifications.redis_client", mock_redis):
        from app.services.notifications import push, get_notifications, Priority
        push(1, "Low", "low msg", Priority.LOW)
        push(1, "Critical", "critical msg", Priority.CRITICAL)
        push(1, "Medium", "med msg", Priority.MEDIUM)
        notifs = get_notifications(1)
        assert notifs[0]["priority_name"] == "CRITICAL"

def test_dedup_suppresses(mock_redis):
    with patch("app.services.notifications.redis_client", mock_redis):
        from app.services.notifications import push, unread_count, Priority
        push(1, "Dup", "body", Priority.MEDIUM, dedup_key="dup-001")
        result = push(1, "Dup", "body", Priority.MEDIUM, dedup_key="dup-001")
        assert result is False

def test_group_batching(mock_redis):
    with patch("app.services.notifications.redis_client", mock_redis):
        from app.services.notifications import push, get_group, Priority
        push(1, "Bill 1", "b1", Priority.MEDIUM, group="bills")
        push(1, "Bill 2", "b2", Priority.MEDIUM, group="bills")
        group = get_group(1, "bills")
        assert len(group) == 2
