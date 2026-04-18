"""Tests for the background job queue system."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def job_queue_module():
    """Import job_queue with mocked Redis and DB."""
    with patch("app.services.job_queue.redis_client") as mock_redis, \
         patch("app.services.job_queue.db") as mock_db:
        from app.services import job_queue
        yield job_queue, mock_redis, mock_db


@pytest.fixture
def worker_module():
    """Import job_worker with mocked dependencies."""
    with patch("app.services.job_worker.redis_client") as mock_redis, \
         patch("app.services.job_worker.db") as mock_db:
        from app.services import job_worker
        yield job_worker, mock_redis, mock_db


class TestJobQueue:
    """Tests for job_queue service."""

    def test_enqueue_creates_redis_entry(self, job_queue_module):
        jq, mock_redis, mock_db = job_queue_module
        mock_redis.zadd.return_value = 1

        job_id = jq.enqueue(
            job_type="test_job",
            payload={"key": "value"},
            priority=3,
        )

        assert job_id is not None
        assert len(job_id) == 36  # UUID format
        mock_redis.set.assert_called_once()
        mock_redis.zadd.assert_called_once()

    def test_enqueue_custom_job_id(self, job_queue_module):
        jq, mock_redis, mock_db = job_queue_module

        job_id = jq.enqueue(
            job_type="test_job",
            job_id="custom-id-123",
        )

        assert job_id == "custom-id-123"

    def test_get_queue_stats(self, job_queue_module):
        jq, mock_redis, mock_db = job_queue_module
        mock_redis.zcard.return_value = 5
        mock_redis.llen.return_value = 2

        # Mock DB query result
        mock_row = MagicMock()
        mock_row.status = "pending"
        mock_row.count = 10
        mock_db.session.execute.return_value.fetchall.return_value = [mock_row]

        stats = jq.get_queue_stats()
        assert "queued" in stats
        assert stats["queued"] == 5

    def test_cancel_job(self, job_queue_module):
        jq, mock_redis, mock_db = job_queue_module

        meta = {
            "job_id": "test-123",
            "status": "pending",
            "priority": 5,
        }
        mock_redis.get.return_value = json.dumps(meta)

        result = jq.cancel_job("test-123")
        assert result is True

    def test_cancel_running_job_fails(self, job_queue_module):
        jq, mock_redis, mock_db = job_queue_module

        meta = {
            "job_id": "test-123",
            "status": "running",
        }
        mock_redis.get.return_value = json.dumps(meta)

        result = jq.cancel_job("test-123")
        assert result is False

    def test_retry_dead_job(self, job_queue_module):
        jq, mock_redis, mock_db = job_queue_module

        meta = {
            "job_id": "test-123",
            "status": "dead",
            "priority": 5,
        }
        mock_redis.get.return_value = json.dumps(meta)

        result = jq.retry_dead_job("test-123")
        assert result is True
        mock_redis.zadd.assert_called()


class TestJobWorker:
    """Tests for job_worker service."""

    def test_register_handler(self, worker_module):
        jw, mock_redis, mock_db = worker_module

        @jw.register_handler("test_handler")
        def handler(payload):
            return {"ok": True}

        assert jw.get_handler("test_handler") is not None

    def test_backoff_computation(self, worker_module):
        jw, mock_redis, mock_db = worker_module

        assert jw._compute_backoff(0) == 5
        assert jw._compute_backoff(1) == 10
        assert jw._compute_backoff(2) == 20
        assert jw._compute_backoff(3) == 40
        # Capped at 3600
        assert jw._compute_backoff(20) == 3600

    def test_process_empty_queue(self, worker_module):
        jw, mock_redis, mock_db = worker_module
        mock_redis.zpopmin.return_value = []

        result = jw.process_next_job()
        assert result is False

    def test_process_job_success(self, worker_module):
        jw, mock_redis, mock_db = worker_module

        # Register a test handler
        @jw.register_handler("success_job")
        def success_handler(payload):
            return {"result": "done"}

        job_id = "test-job-123"
        meta = {
            "job_id": job_id,
            "job_type": "success_job",
            "payload": {},
            "attempts": 0,
            "max_retries": 5,
            "priority": 5,
        }

        mock_redis.zpopmin.return_value = [(job_id, 5.0)]
        mock_redis.set.return_value = True  # lock acquired
        mock_redis.get.return_value = json.dumps(meta, default=str)

        result = jw.process_next_job()
        assert result is True

    def test_process_job_failure_with_retry(self, worker_module):
        jw, mock_redis, mock_db = worker_module

        @jw.register_handler("fail_job")
        def fail_handler(payload):
            raise RuntimeError("Something went wrong")

        job_id = "test-job-456"
        meta = {
            "job_id": job_id,
            "job_type": "fail_job",
            "payload": {},
            "attempts": 0,
            "max_retries": 3,
            "priority": 5,
        }

        mock_redis.zpopmin.return_value = [(job_id, 5.0)]
        mock_redis.set.return_value = True
        mock_redis.get.return_value = json.dumps(meta, default=str)

        result = jw.process_next_job()
        assert result is True
        # Should have been re-added to queue for retry
        mock_redis.zadd.assert_called()

    def test_process_job_failure_dead_letter(self, worker_module):
        jw, mock_redis, mock_db = worker_module

        @jw.register_handler("fail_forever")
        def fail_handler(payload):
            raise RuntimeError("Permanent failure")

        job_id = "test-job-789"
        meta = {
            "job_id": job_id,
            "job_type": "fail_forever",
            "payload": {},
            "attempts": 4,  # Already tried 4 times
            "max_retries": 5,
            "priority": 5,
        }

        mock_redis.zpopmin.return_value = [(job_id, 5.0)]
        mock_redis.set.return_value = True
        mock_redis.get.return_value = json.dumps(meta, default=str)

        result = jw.process_next_job()
        assert result is True
        # Should be pushed to dead letter queue
        mock_redis.lpush.assert_called()

    def test_unknown_handler_marks_dead(self, worker_module):
        jw, mock_redis, mock_db = worker_module

        job_id = "unknown-job"
        meta = {
            "job_id": job_id,
            "job_type": "nonexistent_handler",
            "payload": {},
            "attempts": 0,
            "max_retries": 5,
        }

        mock_redis.zpopmin.return_value = [(job_id, 5.0)]
        mock_redis.set.return_value = True
        mock_redis.get.return_value = json.dumps(meta, default=str)

        result = jw.process_next_job()
        assert result is True
        mock_redis.lpush.assert_called()  # dead letter
