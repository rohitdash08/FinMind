from unittest.mock import MagicMock, patch

def _mock_redis():
    lists = {}
    r = MagicMock()
    def rpush(k,v): lists.setdefault(k,[]).append(v)
    def lrange(k,s,e): return lists.get(k,[])
    def llen(k): return len(lists.get(k,[]))
    r.rpush.side_effect=rpush; r.lrange.side_effect=lrange; r.llen.side_effect=llen
    return r

def test_queue_and_get():
    with patch("app.services.offline_sync.redis_client", _mock_redis()):
        from app.services.offline_sync import queue_operation, get_pending_ops
        queue_operation(1, {"type": "create_expense", "amount": 50})
        ops = get_pending_ops(1)
        assert len(ops) == 1 and ops[0]["type"] == "create_expense"

def test_conflict_last_write_wins():
    from app.services.offline_sync import resolve_conflict
    local = {"id": 1, "amount": 100, "updated_at": 2000}
    server = {"id": 1, "amount": 80, "updated_at": 1000}
    assert resolve_conflict(local, server, "last_write_wins")["amount"] == 100

def test_sync_status():
    with patch("app.services.offline_sync.redis_client", _mock_redis()):
        from app.services.offline_sync import get_sync_status
        status = get_sync_status(999)
        assert status["in_sync"] == True
