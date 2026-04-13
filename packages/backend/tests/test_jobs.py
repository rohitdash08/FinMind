"""Tests for background job retry & monitoring."""

from app.services.jobs import JobManager, JobStatus, with_retry


# 1. Successful job executes once
def test_job_success():
    mgr = JobManager(max_retries=3, base_delay=0.01)
    result = mgr.submit("j1", "test", lambda: "ok")
    assert result.status == JobStatus.SUCCESS
    assert result.attempts == 1
    assert result.last_error is None


# 2. Job retries on failure then succeeds
def test_job_retry_then_success():
    call_count = {"n": 0}
    def flaky():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("transient error")
        return "recovered"
    mgr = JobManager(max_retries=3, base_delay=0.01)
    job = mgr.submit("j2", "flaky", flaky)
    assert job.status == JobStatus.SUCCESS
    assert job.attempts == 3


# 3. Job goes to dead letter after max retries
def test_job_dead_letter():
    def always_fail():
        raise RuntimeError("permanent failure")
    mgr = JobManager(max_retries=2, base_delay=0.01)
    job = mgr.submit("j3", "fail", always_fail)
    assert job.status == JobStatus.DEAD
    assert job.attempts == 3
    assert len(mgr.get_dead_letter_queue()) == 1
    assert mgr.get_dead_letter_queue()[0]["job_id"] == "j3"


# 4. Stats track correctly
def test_stats():
    mgr = JobManager(max_retries=1, base_delay=0.01)
    mgr.submit("s1", "ok", lambda: True)
    mgr.submit("s2", "ok", lambda: True)
    def fail():
        raise RuntimeError("fail")
    mgr.submit("s3", "fail", fail)
    stats = mgr.get_stats()
    assert stats["total_submitted"] == 3
    assert stats["total_succeeded"] == 2
    assert stats["total_failed"] == 1


# 5. Recent jobs returns ordered list
def test_recent_jobs():
    mgr = JobManager(max_retries=0, base_delay=0.01)
    mgr.submit("r1", "first", lambda: True)
    mgr.submit("r2", "second", lambda: True)
    recent = mgr.get_recent_jobs(limit=10)
    assert len(recent) == 2
    assert recent[0]["job_id"] == "r2"  # most recent first


# 6. Get job by ID
def test_get_job():
    mgr = JobManager(max_retries=0, base_delay=0.01)
    mgr.submit("g1", "lookup", lambda: True)
    job = mgr.get_job("g1")
    assert job is not None
    assert job.name == "lookup"
    assert mgr.get_job("nonexistent") is None


# 7. Clear dead letter queue
def test_clear_dead_letter():
    def fail():
        raise RuntimeError("fail")
    mgr = JobManager(max_retries=0, base_delay=0.01)
    mgr.submit("d1", "fail", fail)
    mgr.submit("d2", "fail", fail)
    assert len(mgr.get_dead_letter_queue()) == 2
    cleared = mgr.clear_dead_letter()
    assert cleared == 2
    assert len(mgr.get_dead_letter_queue()) == 0


# 8. Exponential backoff delay calculation
def test_backoff_delay():
    mgr = JobManager(base_delay=1.0, backoff_factor=2.0, max_delay=10.0)
    assert mgr._compute_delay(0) == 1.0
    assert mgr._compute_delay(1) == 2.0
    assert mgr._compute_delay(2) == 4.0
    assert mgr._compute_delay(3) == 8.0
    assert mgr._compute_delay(4) == 10.0  # capped at max_delay


# 9. with_retry decorator
def test_with_retry_decorator():
    call_count = {"n": 0}

    @with_retry(max_retries=2, base_delay=0.01)
    def flaky_func():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise RuntimeError("retry me")
        return "done"

    result = flaky_func()
    assert result == "done"
    assert call_count["n"] == 2


# 10. with_retry decorator raises after exhausting retries
def test_with_retry_exhausted():
    @with_retry(max_retries=1, base_delay=0.01)
    def always_fail():
        raise ValueError("nope")

    try:
        always_fail()
        assert False, "Should have raised"
    except ValueError as e:
        assert "nope" in str(e)


# 11. Job monitoring endpoint - stats (integration)
def test_stats_endpoint(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "total_submitted" in data
    assert "dead_letter_count" in data


# 12. Job monitoring endpoint - auth required
def test_jobs_requires_auth(client):
    r = client.get("/jobs/stats")
    assert r.status_code in (401, 422)
