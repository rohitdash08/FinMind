import os
import sys
from unittest.mock import MagicMock


class FakeRedis:
    def __init__(self, *args, **kwargs):
        self._store = {}

    def scan(self, *args, **kwargs):
        return (0, [])

    def get(self, key, *args, **kwargs):
        return self._store.get(key)

    def set(self, key, value, *args, **kwargs):
        self._store[key] = value
        return True

    def setex(self, key, ttl, value, *args, **kwargs):
        self._store[key] = value
        return True

    def delete(self, *keys, **kwargs):
        for key in keys:
            self._store.pop(key, None)
        return len(keys)

    def flushdb(self, *args, **kwargs):
        self._store.clear()

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    class ConnectionError(Exception):
        pass


fake_redis_mod = MagicMock()
fake_redis_mod.Redis = FakeRedis
fake_redis_mod.from_url = FakeRedis.from_url
fake_redis_mod.ConnectionError = FakeRedis.ConnectionError
sys.modules["redis"] = fake_redis_mod

import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
import app.models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret"


def _setup_db(app):
    with app.app_context():
        db.create_all()


@pytest.fixture()
def app_fixture():
    os.environ.setdefault("FLASK_ENV", "testing")
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
        webhook_signing_secret="test-webhook-secret",
    )
    app = create_app(settings)
    app.config.update(TESTING=True)
    app.config["WEBHOOK_SIGNING_SECRET"] = "test-webhook-secret"
    _setup_db(app)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_fixture):
    return app_fixture.test_client()


@pytest.fixture()
def auth_header(client):
    email = "test@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    register_debug = f"register failed: status={r.status_code}, body={r.get_json()}"
    assert r.status_code in (
        200,
        201,
        409,
    ), register_debug
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}
