"""Tests for job queue architecture (issue #71)."""
import json
from unittest.mock import MagicMock, patch

def _mock_redis():
    store, zsets, lists = {}, {}, {}
    r = MagicMock()
    def zadd(k, m):
        for v,s in m.items(): zsets.setdefault(k,[]).append((s,v))
        zsets[k].sort()
    def zpopmin(k, n):
        if not zsets.get(k): return []
        item = zsets[k].pop(0); return [item]
    def zcard(k): return len(zsets.get(k,[]))
    def setex(k,t,v): store[k]=v
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    def delete(*keys):
        for k in keys: store.pop(k,None)
    def rpush(k,v): lists.setdefault(k,[]).append(v)
    r.zadd.side_effect=zadd; r.zpopmin.side_effect=zpopmin; r.zcard.side_effect=zcard
    r.setex.side_effect=setex; r.get.side_effect=get; r.delete.side_effect=delete
    r.rpush.side_effect=rpush
    return r

def test_submit_and_claim():
    r = _mock_redis()
    with patch("app.services.job_worker.redis_client", r):
        from app.services.job_worker import submit, claim_job
        jid = submit("send_email", {"to": "a@b.com"})
        job = claim_job()
        assert job is not None
        assert job["type"] == "send_email"

def test_complete_job():
    r = _mock_redis()
    with patch("app.services.job_worker.redis_client", r):
        from app.services.job_worker import submit, claim_job, complete_job, get_status
        jid = submit("notify", {})
        claim_job()
        complete_job(jid, result={"sent": True})
        s = get_status(jid)
        assert s["status"] == "completed"

def test_queue_depth():
    r = _mock_redis()
    with patch("app.services.job_worker.redis_client", r):
        from app.services.job_worker import submit, queue_depth
        submit("t1", {}); submit("t2", {})
        assert queue_depth() == 2
