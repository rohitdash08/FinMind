"""Tests for resilient job queue (issue #130)."""
import json, pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_redis():
    store, queues = {}, {}
    r = MagicMock()

    def rpush(key, val):
        queues.setdefault(key, []).append(val)

    def lpop(key):
        q = queues.get(key, [])
        return q.pop(0) if q else None

    def llen(key):
        return len(queues.get(key, []))

    def setex(key, ttl, val):
        store[key] = val

    def get(key):
        v = store.get(key)
        return v.encode() if isinstance(v, str) else v

    r.rpush.side_effect = rpush
    r.lpop.side_effect = lpop
    r.llen.side_effect = llen
    r.setex.side_effect = setex
    r.get.side_effect = get
    return r, store, queues


def test_enqueue_adds_to_queue(mock_redis):
    r, _, queues = mock_redis
    with patch("app.services.job_queue.redis_client", r):
        from app.services.job_queue import enqueue
        jid = enqueue("send_email", {"to": "a@b.com"})
        assert len(queues["jobs:queue"]) == 1
        assert jid is not None


def test_process_success(mock_redis):
    r, store, queues = mock_redis
    with patch("app.services.job_queue.redis_client", r):
        from app.services.job_queue import enqueue, process_one
        jid = enqueue("greet", {"name": "Billy"})
        result = process_one({"greet": lambda p: f"Hello {p['name']}"})
        assert result["result"] == "Hello Billy"


def test_process_retry_on_failure(mock_redis):
    r, store, queues = mock_redis
    with patch("app.services.job_queue.redis_client", r):
        from app.services.job_queue import enqueue, process_one
        enqueue("fail_job", {})
        calls = []
        def handler(p):
            calls.append(1)
            raise ValueError("transient error")
        process_one({"fail_job": handler})
        # Job should be re-queued for retry
        assert len(queues.get("jobs:queue", [])) == 1


def test_dead_queue_after_max_retries(mock_redis):
    r, store, queues = mock_redis
    with patch("app.services.job_queue.redis_client", r):
        from app.services.job_queue import enqueue, process_one, MAX_RETRIES
        enqueue("dead_job", {})
        def always_fail(p): raise RuntimeError("always fails")
        for _ in range(MAX_RETRIES):
            process_one({"dead_job": always_fail})
        assert len(queues.get("jobs:dead", [])) == 1


def test_queue_length(mock_redis):
    r, _, _ = mock_redis
    with patch("app.services.job_queue.redis_client", r):
        from app.services.job_queue import enqueue, queue_length
        enqueue("t1", {}); enqueue("t2", {})
        assert queue_length() == 2
