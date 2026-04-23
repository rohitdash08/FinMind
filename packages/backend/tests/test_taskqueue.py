"""Tests for the background task queue (services/taskqueue.py + routes/tasks.py)."""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.extensions import db as _db, redis_client
from app.models import Task, TaskStatus, User, Role
from app.services import taskqueue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def app():
    """Create app with in-memory SQLite + fake Redis."""
    import app.extensions as ext

    # Patch redis_client to a fake before app is created
    fake_redis = _FakeRedis()
    ext.redis_client = fake_redis
    # Also patch the module-level import in taskqueue
    taskqueue.redis_client = fake_redis

    # Use SQLite for testing
    test_settings = type("S", (), {
        "database_url": "sqlite:///:memory:",
        "redis_url": "redis://fake",
        "jwt_secret": "test-secret",
        "jwt_access_minutes": 15,
        "jwt_refresh_hours": 24,
        "openai_api_key": None,
        "gemini_api_key": None,
        "gemini_model": "gemini-1.5-flash",
        "twilio_account_sid": None,
        "twilio_auth_token": None,
        "twilio_whatsapp_from": None,
        "email_from": None,
        "smtp_url": None,
    })()

    app = create_app(settings=test_settings)

    with app.app_context():
        _db.create_all()
        # Create admin user for testing
        admin = User(
            email="admin@test.com",
            password_hash="x",
            role=Role.ADMIN.value,
        )
        _db.session.add(admin)
        _db.session.commit()

        yield app

        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_token(app, client):
    """Get a JWT token for the admin user."""
    from flask_jwt_extended import create_access_token
    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        token = create_access_token(identity=str(admin.id))
    return token


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Minimal fake Redis (only what taskqueue uses)
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self):
        self._zset = {}  # name -> {member: score}
        self._set = {}   # name -> set
        self._list = {}  # name -> list

    def zadd(self, name, mapping):
        self._zset.setdefault(name, {})
        self._zset[name].update({k: float(v) for k, v in mapping.items()})

    def zrangebyscore(self, name, min_s, max_s, start=0, num=-1):
        items = sorted(self._zset.get(name, {}).items(), key=lambda x: x[1])
        result = [k.encode() for k, v in items if float(min_s) <= v <= float(max_s)]
        if num == -1:
            return result[start:]
        return result[start:start + num]

    def zrem(self, name, *members):
        zs = self._zset.get(name, {})
        removed = 0
        for m in members:
            key = m.decode() if isinstance(m, bytes) else m
            if key in zs:
                del zs[key]
                removed += 1
        return removed

    def zcard(self, name):
        return len(self._zset.get(name, {}))

    def sadd(self, name, *members):
        self._set.setdefault(name, set())
        for m in members:
            self._set[name].add(m.decode() if isinstance(m, bytes) else m)
        return len(members)

    def srem(self, name, *members):
        s = self._set.get(name, set())
        removed = 0
        for m in members:
            key = m.decode() if isinstance(m, bytes) else m
            if key in s:
                s.discard(key)
                removed += 1
        return removed

    def scard(self, name):
        return len(self._set.get(name, set()))

    def rpush(self, name, *values):
        self._list.setdefault(name, [])
        for v in values:
            self._list[name].append(v)
        return len(self._list[name])

    def llen(self, name):
        return len(self._list.get(name, []))

    def lrem(self, name, count, value):
        lst = self._list.get(name, [])
        v = str(value)
        before = len(lst)
        self._list[name] = [x for x in lst if str(x) != v]
        return before - len(self._list[name])


# ---------------------------------------------------------------------------
# Tests: enqueue
# ---------------------------------------------------------------------------

class TestEnqueue:
    def test_create_task(self, app):
        with app.app_context():
            task = taskqueue.enqueue("test_type", {"key": "val"})
            assert task.id is not None
            assert task.task_type == "test_type"
            assert task.status == TaskStatus.PENDING
            assert task.max_retries == 3
            assert json.loads(task.payload) == {"key": "val"}

    def test_custom_max_retries(self, app):
        with app.app_context():
            task = taskqueue.enqueue("t", max_retries=5)
            assert task.max_retries == 5

    def test_scheduled_at(self, app):
        with app.app_context():
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            task = taskqueue.enqueue("t", scheduled_at=future)
            assert task.scheduled_at == future


# ---------------------------------------------------------------------------
# Tests: worker
# ---------------------------------------------------------------------------

class TestWorker:
    def test_success(self, app):
        with app.app_context():
            handler = MagicMock(return_value=True)
            taskqueue.register_handler("test_ok", handler)

            task = taskqueue.enqueue("test_ok", {"x": 1})
            ran = taskqueue.process_next_tick()

            assert ran is True
            assert handler.called
            assert task.status == TaskStatus.SUCCESS
            assert task.finished_at is not None

    def test_no_handler_dead_letters(self, app):
        with app.app_context():
            task = taskqueue.enqueue("nonexistent_type")
            ran = taskqueue.process_next_tick()

            assert ran is True
            assert task.status == TaskStatus.DEAD

    def test_retry_on_failure(self, app):
        with app.app_context():
            fail_then_pass = MagicMock(side_effect=[False, True])
            taskqueue.register_handler("flaky", fail_then_pass)

            task = taskqueue.enqueue("flaky", max_retries=3)

            # First run: fails, should retry
            taskqueue.process_next_tick()
            assert task.status == TaskStatus.PENDING
            assert task.attempt == 1
            assert task.next_retry_at is not None

            # Simulate backoff passing: move scheduled_at to now
            task.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            task.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            _db.session.commit()
            fake_redis = taskqueue.redis_client
            fake_redis.zadd(taskqueue._PENDING_KEY, {str(task.id): time.time()})

            # Second run: succeeds
            taskqueue.process_next_tick()
            assert task.status == TaskStatus.SUCCESS
            assert task.attempt == 2

    def test_dead_after_max_retries(self, app):
        with app.app_context():
            always_fail = MagicMock(return_value=False)
            taskqueue.register_handler("alwaysfail", always_fail)

            task = taskqueue.enqueue("alwaysfail", max_retries=2)

            # Attempt 1
            taskqueue.process_next_tick()
            assert task.status == TaskStatus.PENDING

            # Simulate backoff
            task.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            task.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            _db.session.commit()
            taskqueue.redis_client.zadd(taskqueue._PENDING_KEY, {str(task.id): time.time()})

            # Attempt 2 (max_retries=2, attempt was already 1, now 2 = max)
            taskqueue.process_next_tick()
            assert task.status == TaskStatus.DEAD
            assert task.attempt == 2

    def test_exception_caught(self, app):
        with app.app_context():
            raise_handler = MagicMock(side_effect=RuntimeError("boom"))
            taskqueue.register_handler("exploder", raise_handler)

            task = taskqueue.enqueue("exploder", max_retries=1)
            taskqueue.process_next_tick()

            # Should have caught the exception and marked as DEAD (attempt 1 >= max_retries 1)
            assert task.status == TaskStatus.DEAD
            assert "boom" in (task.last_error or "")

    def test_empty_queue(self, app):
        with app.app_context():
            ran = taskqueue.process_next_tick()
            assert ran is False


# ---------------------------------------------------------------------------
# Tests: monitoring routes
# ---------------------------------------------------------------------------

class TestTaskRoutes:
    def test_list_tasks(self, app, client, admin_token):
        with app.app_context():
            taskqueue.enqueue("route_test", {"a": 1})
            _db.session.commit()

        with app.app_context():
            resp = client.get("/tasks", headers=_auth_headers(admin_token))
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data) >= 1
            assert data[0]["task_type"] == "route_test"

    def test_stats(self, app, client, admin_token):
        resp = client.get("/tasks/stats", headers=_auth_headers(admin_token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert "redis_pending" in data
        assert "db_by_status" in data

    def test_forbidden_non_admin(self, app, client):
        with app.app_context():
            user = User(email="user@test.com", password_hash="x", role=Role.USER.value)
            _db.session.add(user)
            _db.session.commit()
            from flask_jwt_extended import create_access_token
            token = create_access_token(identity=str(user.id))

        resp = client.get("/tasks/stats", headers=_auth_headers(token))
        assert resp.status_code == 403

    def test_retry_dead_task(self, app, client, admin_token):
        with app.app_context():
            # Create and dead-letter a task
            raise_h = MagicMock(side_effect=RuntimeError("nope"))
            taskqueue.register_handler("dead_test", raise_h)
            task = taskqueue.enqueue("dead_test", max_retries=1)
            taskqueue.process_next_tick()
            assert task.status == TaskStatus.DEAD

            tid = task.id

        resp = client.post(f"/tasks/{tid}/retry", headers=_auth_headers(admin_token))
        assert resp.status_code == 200

        with app.app_context():
            task = _db.session.get(Task, tid)
            assert task.status == TaskStatus.PENDING
            assert task.attempt == 0

    def test_purge_dead(self, app, client, admin_token):
        with app.app_context():
            raise_h = MagicMock(side_effect=RuntimeError("die"))
            taskqueue.register_handler("purge_test", raise_h)
            taskqueue.enqueue("purge_test", max_retries=1)
            taskqueue.process_next_tick()

        resp = client.post("/tasks/purge?older_than_hours=0", headers=_auth_headers(admin_token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["purged"] >= 1

    def test_filter_by_status(self, app, client, admin_token):
        with app.app_context():
            taskqueue.enqueue("filter_test")

        resp = client.get("/tasks?status=PENDING", headers=_auth_headers(admin_token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(t["status"] == "PENDING" for t in data)

    def test_invalid_status_filter(self, client, admin_token):
        resp = client.get("/tasks?status=INVALID", headers=_auth_headers(admin_token))
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests: queue_stats helper
# ---------------------------------------------------------------------------

class TestQueueStats:
    def test_counts(self, app):
        with app.app_context():
            taskqueue.enqueue("stat_test")
            stats = taskqueue.queue_stats()
            assert stats["redis_pending"] >= 1
            assert "PENDING" in stats["db_by_status"]
            assert stats["db_by_status"]["PENDING"] >= 1
