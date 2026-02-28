"""Tests for resilient background job retry and monitoring."""

import pytest
from app.services.job_retry import (
    RetryConfig,
    JobRecord,
    JobMonitor,
    JobStatus,
    with_retry,
    get_monitor,
)


class TestRetryConfig:
    def test_default(self):
        c = RetryConfig()
        assert c.max_retries == 3
        assert c.base_delay == 1.0

    def test_exponential_delay(self):
        c = RetryConfig(base_delay=1.0, backoff_factor=2.0, max_delay=300)
        assert c.get_delay(0) == 1.0
        assert c.get_delay(1) == 2.0
        assert c.get_delay(2) == 4.0
        assert c.get_delay(3) == 8.0

    def test_max_delay_cap(self):
        c = RetryConfig(base_delay=100, backoff_factor=10, max_delay=300)
        assert c.get_delay(5) == 300


class TestJobRecord:
    def test_to_dict(self):
        r = JobRecord("abc", "test_job", (), {})
        d = r.to_dict()
        assert d["job_id"] == "abc"
        assert d["name"] == "test_job"
        assert d["status"] == "pending"
        assert d["attempts"] == 0


class TestJobMonitor:
    def test_register_and_get(self):
        m = JobMonitor()
        r = JobRecord("j1", "test", (), {})
        m.register(r)
        assert m.get("j1") is not None
        assert m.get("j1").name == "test"

    def test_get_missing(self):
        m = JobMonitor()
        assert m.get("missing") is None

    def test_dead_letter(self):
        m = JobMonitor()
        r = JobRecord("j1", "test", (), {})
        r.status = JobStatus.DEAD
        m.add_to_dead_letter(r)
        dlq = m.dead_letter_queue()
        assert len(dlq) == 1
        assert dlq[0]["status"] == "dead"

    def test_stats(self):
        m = JobMonitor()
        r1 = JobRecord("j1", "a", (), {})
        r1.status = JobStatus.SUCCESS
        r1.duration_ms = 100
        r2 = JobRecord("j2", "b", (), {})
        r2.status = JobStatus.FAILED
        m.register(r1)
        m.register(r2)
        s = m.stats()
        assert s["total_jobs"] == 2
        assert s["by_status"]["success"] == 1
        assert s["by_status"]["failed"] == 1

    def test_recent(self):
        m = JobMonitor()
        for i in range(5):
            r = JobRecord(f"j{i}", f"job{i}", (), {})
            m.register(r)
        recent = m.recent(limit=3)
        assert len(recent) == 3

    def test_max_history(self):
        m = JobMonitor(max_history=3)
        for i in range(5):
            r = JobRecord(f"j{i}", f"job{i}", (), {})
            m.register(r)
        assert len(m._jobs) == 3


class TestWithRetry:
    def test_success_no_retry(self):
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        def good_job():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = good_job()
        assert result == "ok"
        assert call_count == 1

    def test_retry_then_success(self):
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        def flaky_job():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary error")
            return "recovered"

        result = flaky_job()
        assert result == "recovered"
        assert call_count == 3

    def test_exhaust_retries(self):
        @with_retry(RetryConfig(max_retries=2, base_delay=0.01))
        def bad_job():
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError):
            bad_job()


class TestJobsAPI:
    def test_stats(self, client):
        resp = client.get("/jobs/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_jobs" in data

    def test_recent(self, client):
        resp = client.get("/jobs/recent")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_dead_letter(self, client):
        resp = client.get("/jobs/dead-letter")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_missing_job(self, client):
        resp = client.get("/jobs/nonexistent")
        assert resp.status_code == 404
