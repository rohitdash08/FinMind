"""Comprehensive tests for the resilient background job queue system.

Covers: enqueue, processing, retries, backoff, dead-letter queue,
idempotency, timeouts, monitoring, admin routes, and reminder integration.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.extensions import db, redis_client
from app.models import Role, User
from app.services.job_queue import (
    DEFAULT_RETRY,
    Job,
    JobQueue,
    JobState,
    RetryPolicy,
    job_queue,
)
from app.services.job_monitor import AlertThresholds, JobMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal in-memory Redis mock for unit tests that don't need real Redis."""

    def __init__(self):
        self._data = {}
        self._sorted_sets = {}
        self._sets = {}

    def hset(self, key, mapping=None, **kwargs):
        if key not in self._data:
            self._data[key] = {}
        if mapping:
            self._data[key].update(mapping)
        self._data[key].update(kwargs)

    def hgetall(self, key):
        return dict(self._data.get(key, {}))

    def hget(self, key, field):
        return self._data.get(key, {}).get(field)

    def hincrby(self, key, field, amount=1):
        if key not in self._data:
            self._data[key] = {}
        current = int(self._data[key].get(field, 0))
        self._data[key][field] = str(current + amount)
        return current + amount

    def hincrbyfloat(self, key, field, amount):
        if key not in self._data:
            self._data[key] = {}
        current = float(self._data[key].get(field, 0))
        self._data[key][field] = str(round(current + amount, 4))
        return current + amount

    def delete(self, *keys):
        for key in keys:
            self._data.pop(key, None)
            self._sorted_sets.pop(key, None)
            self._sets.pop(key, None)

    def keys(self, pattern="*"):
        import fnmatch
        all_keys = set(self._data.keys()) | set(self._sorted_sets.keys()) | set(self._sets.keys())
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]

    # Sorted set operations
    def zadd(self, key, mapping):
        if key not in self._sorted_sets:
            self._sorted_sets[key] = {}
        self._sorted_sets[key].update(mapping)

    def zrem(self, key, *members):
        ss = self._sorted_sets.get(key, {})
        removed = 0
        for m in members:
            if m in ss:
                del ss[m]
                removed += 1
        return removed

    def zcard(self, key):
        return len(self._sorted_sets.get(key, {}))

    def zrange(self, key, start, stop):
        ss = self._sorted_sets.get(key, {})
        items = sorted(ss.items(), key=lambda x: x[1])
        if stop == -1:
            stop = len(items)
        else:
            stop += 1
        return [k for k, v in items[start:stop]]

    def zrevrange(self, key, start, stop):
        ss = self._sorted_sets.get(key, {})
        items = sorted(ss.items(), key=lambda x: x[1], reverse=True)
        return [k for k, v in items[start:stop + 1]]

    def zrangebyscore(self, key, min_score, max_score, start=0, num=None):
        ss = self._sorted_sets.get(key, {})
        min_val = float("-inf") if min_score == "-inf" else float(min_score)
        max_val = float("inf") if max_score == "+inf" else float(max_score)
        items = sorted(
            [(k, v) for k, v in ss.items() if min_val <= v <= max_val],
            key=lambda x: x[1],
        )
        if num is not None:
            items = items[start:start + num]
        return [k for k, v in items]

    def zremrangebyrank(self, key, start, stop):
        ss = self._sorted_sets.get(key, {})
        items = sorted(ss.items(), key=lambda x: x[1])
        if stop < 0:
            stop = len(items) + stop + 1
        else:
            stop += 1
        to_remove = [k for k, v in items[start:stop]]
        for k in to_remove:
            del ss[k]
        return len(to_remove)

    # Set operations
    def sadd(self, key, *members):
        if key not in self._sets:
            self._sets[key] = set()
        self._sets[key].update(members)

    def srem(self, key, *members):
        s = self._sets.get(key, set())
        removed = 0
        for m in members:
            if m in s:
                s.remove(m)
                removed += 1
        return removed

    def scard(self, key):
        return len(self._sets.get(key, set()))

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def hincrbyfloat(self, key, field, amount):
        self._ops.append(("hincrbyfloat", key, field, amount))
        return self

    def hincrby(self, key, field, amount=1):
        self._ops.append(("hincrby", key, field, amount))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "hincrbyfloat":
                results.append(self._redis.hincrbyfloat(op[1], op[2], op[3]))
            elif op[0] == "hincrby":
                results.append(self._redis.hincrby(op[1], op[2], op[3]))
        return results


def make_queue() -> JobQueue:
    """Create a JobQueue with a fresh FakeRedis."""
    return JobQueue(redis=FakeRedis())


# ---------------------------------------------------------------------------
# Unit tests: RetryPolicy
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    def test_exponential_backoff(self):
        p = RetryPolicy(base_delay=2.0, backoff="exponential")
        assert p.delay_for(1) == 2.0
        assert p.delay_for(2) == 4.0
        assert p.delay_for(3) == 8.0
        assert p.delay_for(4) == 16.0

    def test_linear_backoff(self):
        p = RetryPolicy(base_delay=5.0, backoff="linear")
        assert p.delay_for(1) == 5.0
        assert p.delay_for(2) == 10.0
        assert p.delay_for(3) == 15.0

    def test_max_delay_cap(self):
        p = RetryPolicy(base_delay=100.0, backoff="exponential", max_delay=300.0)
        assert p.delay_for(1) == 100.0
        assert p.delay_for(2) == 200.0
        assert p.delay_for(3) == 300.0  # capped
        assert p.delay_for(10) == 300.0  # still capped


# ---------------------------------------------------------------------------
# Unit tests: Job serialisation
# ---------------------------------------------------------------------------

class TestJobSerialization:
    def test_roundtrip(self):
        job = Job(
            id="test-123",
            job_type="send_email",
            payload={"to": "user@example.com"},
            state=JobState.PENDING.value,
            created_at=time.time(),
            updated_at=time.time(),
        )
        d = job.to_dict()
        restored = Job.from_dict(d)
        assert restored.id == "test-123"
        assert restored.job_type == "send_email"
        assert restored.payload == {"to": "user@example.com"}

    def test_from_dict_string_fields(self):
        """Redis stores everything as strings; from_dict must coerce."""
        data = {
            "id": "abc",
            "job_type": "test",
            "payload": '{"key": "val"}',
            "state": "PENDING",
            "retry_policy": '{"max_retries": 5, "backoff": "linear", "base_delay": 1.0, "max_delay": 60.0}',
            "attempts": "2",
            "max_retries": "5",
            "created_at": "1700000000.0",
            "updated_at": "1700000000.0",
            "timeout": "120",
        }
        job = Job.from_dict(data)
        assert job.payload == {"key": "val"}
        assert job.attempts == 2
        assert job.max_retries == 5
        assert job.timeout == 120


# ---------------------------------------------------------------------------
# Unit tests: JobQueue
# ---------------------------------------------------------------------------

class TestJobQueue:
    def test_enqueue_and_process(self):
        q = make_queue()
        results = []

        @q.handler("greet")
        def handle(payload):
            results.append(f"Hello {payload['name']}")
            return {"greeted": True}

        job_id = q.enqueue("greet", payload={"name": "Alice"})
        assert q.queue_depth() == 1

        processed = q.process_next()
        assert processed is True
        assert results == ["Hello Alice"]
        assert q.queue_depth() == 0

        job = q.get_job(job_id)
        assert job["state"] == JobState.SUCCESS.value
        assert job["result"] == {"greeted": True}

    def test_empty_queue_returns_false(self):
        q = make_queue()
        assert q.process_next() is False

    def test_handler_failure_triggers_retry(self):
        q = make_queue()
        call_count = 0

        @q.handler("flaky")
        def handle(payload):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return {"ok": True}

        q.enqueue(
            "flaky",
            retry_policy=RetryPolicy(max_retries=3, backoff="linear", base_delay=0),
        )

        # First attempt — fails, schedules retry
        q.process_next()
        assert call_count == 1
        assert q.queue_depth() == 1  # re-enqueued

        # Second attempt — fails again
        q.process_next()
        assert call_count == 2
        assert q.queue_depth() == 1

        # Third attempt — succeeds
        q.process_next()
        assert call_count == 3
        job_id = list(q._redis._sorted_sets.get("finmind:jobs:completed", {}).keys())[0]
        job = q.get_job(job_id)
        assert job["state"] == JobState.SUCCESS.value

    def test_exhausted_retries_move_to_dlq(self):
        q = make_queue()

        @q.handler("always_fail")
        def handle(payload):
            raise ValueError("permanent error")

        q.enqueue(
            "always_fail",
            retry_policy=RetryPolicy(max_retries=2, backoff="linear", base_delay=0),
        )

        # Attempt 1 — fails, retry
        q.process_next()
        assert q.queue_depth() == 1
        assert q.dlq_count() == 0

        # Attempt 2 — fails, exhausted → DLQ
        q.process_next()
        assert q.queue_depth() == 0
        assert q.dlq_count() == 1

        dlq = q.list_dead_letter()
        assert len(dlq) == 1
        assert dlq[0]["state"] == JobState.DEAD.value
        assert "permanent error" in dlq[0]["error"]

    def test_idempotency_skips_duplicate(self):
        q = make_queue()
        q.register_handler("noop", lambda p: {"ok": True})

        id1 = q.enqueue("noop", job_id="unique-123")
        id2 = q.enqueue("noop", job_id="unique-123")  # duplicate

        assert id1 == id2
        assert q.queue_depth() == 1  # only one job

    def test_idempotency_allows_requeue_after_success(self):
        q = make_queue()
        q.register_handler("noop", lambda p: {"ok": True})

        q.enqueue("noop", job_id="re-use")
        q.process_next()  # completes

        # Now same ID should create a new job (old one succeeded)
        q.enqueue("noop", job_id="re-use")
        assert q.queue_depth() == 1

    def test_manual_retry_from_dlq(self):
        q = make_queue()
        attempt = 0

        @q.handler("retry_me")
        def handle(payload):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise RuntimeError("fail once")
            return {"ok": True}

        q.enqueue(
            "retry_me",
            retry_policy=RetryPolicy(max_retries=1, backoff="linear", base_delay=0),
        )
        q.process_next()  # exhausted → DLQ
        assert q.dlq_count() == 1

        dlq = q.list_dead_letter()
        job_id = dlq[0]["id"]

        # Manual retry
        success = q.retry_job(job_id)
        assert success is True
        assert q.dlq_count() == 0
        assert q.queue_depth() == 1

        # Process the retried job — succeeds now
        q.process_next()
        job = q.get_job(job_id)
        assert job["state"] == JobState.SUCCESS.value

    def test_clear_dead_letter(self):
        q = make_queue()

        @q.handler("fail_hard")
        def handle(payload):
            raise RuntimeError("boom")

        q.enqueue(
            "fail_hard",
            job_id="dlq-test",
            retry_policy=RetryPolicy(max_retries=1, backoff="linear", base_delay=0),
        )
        q.process_next()  # → DLQ
        assert q.dlq_count() == 1

        cleared = q.clear_dead_letter("dlq-test")
        assert cleared is True
        assert q.dlq_count() == 0
        assert q.get_job("dlq-test") is None

    def test_no_handler_moves_to_dlq(self):
        q = make_queue()
        q.enqueue("unknown_type", payload={})
        q.process_next()
        assert q.dlq_count() == 1

    def test_process_batch(self):
        q = make_queue()
        processed_ids = []

        @q.handler("batch")
        def handle(payload):
            processed_ids.append(payload["n"])
            return {}

        for i in range(5):
            q.enqueue("batch", payload={"n": i})

        count = q.process_batch(max_jobs=3)
        assert count == 3
        assert len(processed_ids) == 3

    def test_delayed_job_not_processed_early(self):
        q = make_queue()
        q.register_handler("delayed", lambda p: {"ok": True})

        q.enqueue("delayed", delay=9999)
        assert q.queue_depth() == 1

        processed = q.process_next()
        assert processed is False  # not eligible yet

    def test_metrics_tracking(self):
        q = make_queue()
        q.register_handler("metric_test", lambda p: {"ok": True})

        q.enqueue("metric_test")
        q.process_next()

        metrics = q.get_metrics()
        assert int(metrics.get("enqueued", 0)) == 1
        assert int(metrics.get("succeeded", 0)) == 1

    def test_list_failed_includes_retrying_jobs(self):
        q = make_queue()

        @q.handler("semi_fail")
        def handle(payload):
            raise RuntimeError("oops")

        q.enqueue(
            "semi_fail",
            retry_policy=RetryPolicy(max_retries=5, backoff="linear", base_delay=0),
        )
        q.process_next()  # fails, but still has retries left

        failed = q.list_failed()
        assert len(failed) == 1
        assert failed[0]["state"] == JobState.FAILED.value

    def test_flush_all(self):
        q = make_queue()
        q.register_handler("flush_test", lambda p: {})
        q.enqueue("flush_test")
        q.flush_all()
        assert q.queue_depth() == 0


# ---------------------------------------------------------------------------
# Unit tests: JobMonitor
# ---------------------------------------------------------------------------

class TestJobMonitor:
    def test_dashboard_status_empty_queue(self):
        q = make_queue()
        monitor = JobMonitor(queue=q)
        status = monitor.dashboard_status()

        assert status["queue_depth"] == 0
        assert status["active_workers"] == 0
        assert status["metrics"]["success_rate"] == 1.0
        assert status["alerts"] == []

    def test_dashboard_status_with_data(self):
        q = make_queue()
        q.register_handler("ok_job", lambda p: {"done": True})
        for _ in range(3):
            q.enqueue("ok_job")
            q.process_next()

        monitor = JobMonitor(queue=q)
        status = monitor.dashboard_status()

        assert status["metrics"]["succeeded"] == 3
        assert status["metrics"]["success_rate"] == 1.0
        assert status["completed"] == 3

    def test_alerts_on_high_failure_rate(self):
        q = make_queue()

        @q.handler("fail_always")
        def handle(payload):
            raise RuntimeError("fail")

        for _ in range(5):
            q.enqueue(
                "fail_always",
                retry_policy=RetryPolicy(max_retries=1, backoff="linear", base_delay=0),
            )
            q.process_next()  # → DLQ

        monitor = JobMonitor(
            queue=q,
            thresholds=AlertThresholds(max_failure_rate=0.1),
        )
        status = monitor.dashboard_status()
        alert_types = [a["type"] for a in status["alerts"]]
        assert "high_failure_rate" in alert_types

    def test_queue_counts(self):
        q = make_queue()
        q.register_handler("count_test", lambda p: {})
        q.enqueue("count_test")

        monitor = JobMonitor(queue=q)
        counts = monitor.queue_counts()
        assert counts["pending"] == 1
        assert counts["active"] == 0

    def test_execution_metrics(self):
        q = make_queue()
        q.register_handler("metrics_job", lambda p: {})
        q.enqueue("metrics_job")
        q.process_next()

        monitor = JobMonitor(queue=q)
        metrics = monitor.job_execution_metrics()
        assert metrics["total_succeeded"] == 1
        assert metrics["success_rate"] == 1.0


# ---------------------------------------------------------------------------
# Integration tests: Admin routes (require Flask app context)
# ---------------------------------------------------------------------------

def _create_admin_user(client):
    """Register a user and promote to admin, return auth header."""
    email = "admin@example.com"
    password = "adminpass123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]

    # Promote to admin
    from app.extensions import db
    from app.models import User, Role

    with client.application.app_context():
        user = db.session.query(User).filter_by(email=email).first()
        user.role = Role.ADMIN.value
        db.session.commit()

    return {"Authorization": f"Bearer {access}"}


class TestJobRoutes:
    def test_status_requires_admin(self, client, auth_header):
        """Regular users should get 403."""
        r = client.get("/jobs/status", headers=auth_header)
        assert r.status_code == 403

    def test_status_returns_dashboard_data(self, client):
        admin_header = _create_admin_user(client)
        r = client.get("/jobs/status", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "queue_depth" in data
        assert "metrics" in data
        assert "alerts" in data

    def test_failed_endpoint(self, client):
        admin_header = _create_admin_user(client)
        r = client.get("/jobs/failed", headers=admin_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "jobs" in data
        assert "count" in data

    def test_retry_nonexistent_job(self, client):
        admin_header = _create_admin_user(client)
        r = client.post("/jobs/retry/nonexistent-id", headers=admin_header)
        assert r.status_code == 404

    def test_clear_nonexistent_dlq(self, client):
        admin_header = _create_admin_user(client)
        r = client.delete("/jobs/dead-letter/nonexistent-id", headers=admin_header)
        assert r.status_code == 404

    def test_unauthenticated_access(self, client):
        r = client.get("/jobs/status")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests: Reminder job queue integration
# ---------------------------------------------------------------------------

class TestReminderJobIntegration:
    def test_run_due_with_queue_param(self, client, auth_header):
        """POST /reminders/run?queue=true should enqueue rather than send inline."""
        from datetime import datetime, timedelta

        # Create a reminder that's due
        send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        r = client.post(
            "/reminders",
            json={"message": "Pay rent", "send_at": send_at, "channel": "email"},
            headers=auth_header,
        )
        assert r.status_code == 201

        # Use queue mode
        r = client.post("/reminders/run?queue=true", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "enqueued" in data
        assert data["enqueued"] >= 1

    def test_run_due_without_queue_preserves_behavior(self, client, auth_header):
        """Default /reminders/run without ?queue should still work inline."""
        from datetime import datetime, timedelta

        send_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        r = client.post(
            "/reminders",
            json={"message": "Pay bills", "send_at": send_at, "channel": "email"},
            headers=auth_header,
        )
        assert r.status_code == 201

        r = client.post("/reminders/run", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "processed" in data
