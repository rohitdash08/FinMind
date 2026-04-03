"""Tests for background job retry & monitoring system."""

import json
import time
from unittest.mock import patch, MagicMock


class MockRedis:
    """Minimal Redis mock for testing."""
    def __init__(self):
        self._store = {}
        self._queues = {}
        self._sets = {}
        self._lists = {}

    def hset(self, key, mapping=None, **kwargs):
        if key not in self._store:
            self._store[key] = {}
        if mapping:
            self._store[key].update({k: str(v) if v is not None else "" for k, v in mapping.items()})

    def hgetall(self, key):
        return self._store.get(key, {})

    def hget(self, key, field):
        return self._store.get(key, {}).get(field)

    def rpush(self, key, value):
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].append(value)

    def blpop(self, key, timeout=0):
        k = key if isinstance(key, str) else key[0] if isinstance(key, list) else "finmind:jobs:queue"
        if self._lists.get(k):
            return (k, self._lists[k].pop(0))
        return None

    def llen(self, key):
        return len(self._lists.get(key, []))

    def sadd(self, key, *members):
        if key not in self._sets:
            self._sets[key] = set()
        self._sets[key].update(members)

    def srem(self, key, *members):
        if key in self._sets:
            self._sets[key] -= set(members)

    def scard(self, key):
        return len(self._sets.get(key, set()))

    def lrem(self, key, count, value):
        if key in self._lists:
            try:
                self._lists[key].remove(value)
            except ValueError:
                pass

    def lpush(self, key, value):
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].insert(0, value)

    def ltrim(self, key, start, end):
        if key in self._lists:
            self._lists[key] = self._lists[key][start:end + 1]

    def keys(self, pattern):
        import re
        regex = pattern.replace("*", ".*")
        return [k for k in self._store if re.match(regex, k)]

    def pipeline(self):
        return MockPipeline(self)

    def sismember(self, key, member):
        return member in self._sets.get(key, set())


class MockPipeline:
    def __init__(self, redis_mock):
        self._redis = redis_mock
        self._ops = []

    def hset(self, key, mapping=None, **kwargs):
        self._ops.append(("hset", key, mapping, kwargs))
        return self

    def rpush(self, key, value):
        self._ops.append(("rpush", key, value))
        return self

    def execute(self):
        for op in self._ops:
            if op[0] == "hset":
                self._redis.hset(op[1], mapping=op[2], **op[3])
            elif op[0] == "rpush":
                self._redis.rpush(op[1], op[2])
        self._ops = []


mock_redis = MockRedis()


def test_enqueue_job():
    """Test that a job can be enqueued."""
    from packages.backend.app.services.job_queue import enqueue, QUEUE_KEY, JOB_PREFIX

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue("send_email", {"to": "test@example.com", "subject": "Test"})
        assert job_id is not None
        assert len(job_id) == 36  # UUID format

        # Check job stored in Redis
        job_data = mock_redis.hgetall(f"{JOB_PREFIX}{job_id}")
        assert job_data["task_name"] == "send_email"
        assert job_data["status"] == "PENDING"

        # Check queued
        assert mock_redis.llen(QUEUE_KEY) == 1


def test_dequeue_job():
    """Test that a job can be dequeued and marked as running."""
    from packages.backend.app.services.job_queue import enqueue, dequeue, JobStatus, JOB_PREFIX

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue("generate_report", {"user_id": 1})
        job = dequeue(timeout=1)

        assert job is not None
        assert job["id"] == job_id
        assert job["status"] == JobStatus.RUNNING.value


def test_mark_success():
    """Test marking a job as succeeded."""
    from packages.backend.app.services.job_queue import enqueue, dequeue, mark_success, JOB_PREFIX

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue("test_task", {"data": "test"})
        dequeue(timeout=1)
        mark_success(job_id)

        job_data = mock_redis.hgetall(f"{JOB_PREFIX}{job_id}")
        assert job_data["status"] == "SUCCEEDED"
        assert job_data["finished_at"] is not None


def test_mark_failed_retries():
    """Test that a failed job is retried with exponential backoff."""
    from packages.backend.app.services.job_queue import (
        enqueue, dequeue, mark_failed, JobStatus, JOB_PREFIX,
    )

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue("flaky_task", {"attempt": 1}, retry_policy=__import__(
            "packages.backend.app.services.job_queue", fromlist=["RetryPolicy"]
        ).RetryPolicy(max_retries=3, base_delay_seconds=1))
        dequeue(timeout=1)
        mark_failed(job_id, "temporary error")

        job_data = mock_redis.hgetall(f"{JOB_PREFIX}{job_id}")
        assert job_data["status"] == "RETRYING"
        assert job_data["attempt"] == "1"
        assert "temporary error" in job_data["error"]


def test_max_retries_dead_letter():
    """Test that a job exceeding max retries goes to dead letter queue."""
    from packages.backend.app.services.job_queue import (
        enqueue, dequeue, mark_failed, JobStatus, DEAD_LETTER_KEY, JOB_PREFIX,
        RetryPolicy,
    )

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue(
            "doomed_task", {},
            retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.1),
        )
        dequeue(timeout=1)
        mark_failed(job_id, "first failure")  # attempt 1, retries
        dequeue(timeout=1)
        mark_failed(job_id, "second failure")  # attempt 2 > max_retries=1, dead

        job_data = mock_redis.hgetall(f"{JOB_PREFIX}{job_id}")
        assert job_data["status"] == "DEAD"


def test_get_stats():
    """Test job queue statistics."""
    from packages.backend.app.services.job_queue import enqueue, get_stats

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        enqueue("task1", {})
        enqueue("task2", {})
        stats = get_stats()
        assert stats["queue_length"] >= 2
        assert stats["total_jobs"] >= 2


def test_get_job():
    """Test retrieving a specific job."""
    from packages.backend.app.services.job_queue import enqueue, get_job

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue("lookup_task", {"key": "value"})
        job = get_job(job_id)
        assert job is not None
        assert job["task_name"] == "lookup_task"


def test_get_job_not_found():
    """Test looking up non-existent job."""
    from packages.backend.app.services.job_queue import get_job

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job = get_job("nonexistent-id")
        assert job is None


def test_retry_policy_delay():
    """Test exponential backoff calculation."""
    from packages.backend.app.services.job_queue import RetryPolicy

    policy = RetryPolicy(base_delay_seconds=5, backoff_multiplier=2, max_delay_seconds=300)
    assert policy.get_delay(0) == 5.0
    assert policy.get_delay(1) == 10.0
    assert policy.get_delay(2) == 20.0
    assert policy.get_delay(10) == 300.0  # capped


def test_retry_dead_job():
    """Test re-queuing a dead job."""
    from packages.backend.app.services.job_queue import (
        enqueue, dequeue, mark_failed, retry_dead_job, JobStatus, JOB_PREFIX,
        RetryPolicy,
    )

    with patch("packages.backend.app.services.job_queue.redis_client", mock_redis):
        job_id = enqueue("retry_me", {}, retry_policy=RetryPolicy(max_retries=0))
        dequeue(timeout=1)
        mark_failed(job_id, "failed immediately")  # goes to dead

        success = retry_dead_job(job_id)
        assert success is True

        job_data = mock_redis.hgetall(f"{JOB_PREFIX}{job_id}")
        assert job_data["status"] == "PENDING"
        assert job_data["attempt"] == "0"
