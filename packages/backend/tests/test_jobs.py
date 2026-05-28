"""
Tests for the background job retry system.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.jobs import (
    Job, JobStatus, RetryPolicy, DEFAULT_RETRY_POLICY,
    enqueue, dequeue, mark_completed, mark_failed,
    process_next, get_dead_letters, purge_dead_letters,
    retry_dead_letter, get_queue_stats,
    register_job_handler, get_job_handler,
    QUEUE_PREFIX, DEAD_LETTER_PREFIX,
)


class TestRetryPolicy:
    def test_default_policy(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.initial_delay_seconds == 1.0
        assert p.backoff_multiplier == 2.0

    def test_delay_increases_exponentially(self):
        p = RetryPolicy(initial_delay_seconds=1.0, backoff_multiplier=2.0)
        assert p.delay_for_attempt(0) == 1.0
        assert p.delay_for_attempt(1) == 2.0
        assert p.delay_for_attempt(2) == 4.0

    def test_delay_capped_at_max(self):
        p = RetryPolicy(initial_delay_seconds=10.0, max_delay_seconds=30.0, backoff_multiplier=3.0)
        assert p.delay_for_attempt(2) == 30.0  # would be 90, capped at 30


class TestJob:
    def test_job_defaults(self):
        job = Job(type="test")
        assert job.id
        assert job.status == JobStatus.PENDING
        assert job.attempts == 0
        assert job.max_retries == 3

    def test_can_retry(self):
        job = Job(type="test", attempts=2, max_retries=3)
        assert job.can_retry is True
        job.attempts = 3
        assert job.can_retry is False

    def test_to_dict_roundtrip(self):
        job = Job(type="email", payload={"to": "test@test.com"}, max_retries=5)
        d = job.to_dict()
        assert d["type"] == "email"
        assert d["payload"]["to"] == "test@test.com"
        restored = Job.from_dict(d)
        assert restored.type == "email"
        assert restored.payload["to"] == "test@test.com"
        assert restored.max_retries == 5

    def test_from_dict_with_string_status(self):
        d = {"type": "test", "status": "running"}
        job = Job.from_dict(d)
        assert job.status == JobStatus.RUNNING


class TestJobQueue:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up Redis keys after each test."""
        yield
        import redis
        from ..config import Settings
        s = Settings()
        r = redis.from_url(s.redis_url)
        for key in r.scan_iter("finmind:jobs:*"):
            r.delete(key)

    def test_enqueue_and_dequeue(self):
        job = enqueue("test_job", {"foo": "bar"}, max_retries=2)
        assert job.type == "test_job"
        assert job.status == JobStatus.PENDING

        dequeued = dequeue("test_job")
        assert dequeued is not None
        assert dequeued.id == job.id
        assert dequeued.status == JobStatus.RUNNING
        assert dequeued.attempts == 1

    def test_dequeue_empty_queue(self):
        result = dequeue("nonexistent")
        assert result is None

    def test_mark_completed(self):
        enqueue("test_job", {"x": 1})
        job = dequeue("test_job")
        mark_completed(job)
        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None

    def test_mark_failed_retry(self):
        enqueue("test_job", {"x": 1}, max_retries=3)
        job = dequeue("test_job")
        result = mark_failed(job, "connection timeout")
        assert result.last_error == "connection timeout"
        # Should be re-queued
        next_job = dequeue("test_job")
        assert next_job is not None
        assert next_job.attempts == 1

    def test_mark_failed_dead_letter(self):
        enqueue("test_job", {"x": 1}, max_retries=1)
        job = dequeue("test_job")
        # First attempt (attempts=1), max_retries=1, can_retry=False
        result = mark_failed(job, "permanent failure")
        assert result.status == JobStatus.DEAD

        dead = get_dead_letters("test_job")
        assert len(dead) == 1
        assert dead[0].id == job.id

    def test_process_next_with_handler(self):
        called = []
        register_job_handler("greet", lambda p: called.append(p["name"]))

        enqueue("greet", {"name": "World"})
        result = process_next("greet")
        assert result.status == JobStatus.COMPLETED
        assert called == ["World"]

    def test_process_next_no_handler(self):
        enqueue("unknown_type", {})
        result = process_next("unknown_type")
        assert result is not None
        assert result.last_error is not None

    def test_process_next_empty(self):
        result = process_next("empty")
        assert result is None

    def test_purge_dead_letters(self):
        enqueue("test_job", {}, max_retries=1)
        job = dequeue("test_job")
        mark_failed(job, "fail")

        count = purge_dead_letters("test_job")
        assert count == 1
        assert get_dead_letters("test_job") == []

    def test_get_queue_stats(self):
        enqueue("test_job", {})
        stats = get_queue_stats("test_job")
        assert stats["job_type"] == "test_job"
        assert stats["pending"] >= 1

    def test_retry_dead_letter(self):
        enqueue("test_job", {}, max_retries=1)
        job = dequeue("test_job")
        mark_failed(job, "fail")

        retried = retry_dead_letter(job.id, "test_job")
        assert retried is not None
        assert retried.attempts == 0
        assert retried.status == JobStatus.PENDING

        # Dead letters should be empty now
        assert get_dead_letters("test_job") == []

    def test_retry_dead_letter_not_found(self):
        result = retry_dead_letter("nonexistent-id", "test_job")
        assert result is None

    def test_handler_registry(self):
        handler = lambda p: None
        register_job_handler("my_type", handler)
        assert get_job_handler("my_type") is handler
        assert get_job_handler("unknown") is None

    def test_exponential_backoff_across_retries(self):
        enqueue("test_job", {}, max_retries=3,
                retry_policy=RetryPolicy(initial_delay_seconds=1.0, backoff_multiplier=2.0))
        job = dequeue("test_job")
        assert job.attempts == 1
        delay1 = job.next_delay()
        mark_failed(job, "fail")

        job2 = dequeue("test_job")
        delay2 = job2.next_delay()
        assert delay2 > delay1  # Exponential increase
