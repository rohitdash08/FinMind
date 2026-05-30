import os
from unittest.mock import MagicMock, patch

import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    # Override defaults for tests
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"  # not used in tests
    jwt_secret: str = "test-secret"


class _FakeRedis:
    def __init__(self):
        self._data: dict[str, str] = {}

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value

    def set(self, key, value):
        self._data[key] = value

    def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)

    def flushdb(self):
        self._data.clear()

    def scan(self, cursor=0, match=None, count=100):
        return (0, [])


def _mock_redis():
    return _FakeRedis()


def _setup_db(app):
    with app.app_context():
        db.create_all()


@pytest.fixture()
def app_fixture():
    os.environ.setdefault("FLASK_ENV", "testing")
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    app = create_app(settings)
    app.config.update(TESTING=True)
    _setup_db(app)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_fixture):
    return app_fixture.test_client()


_REDIS_MOCK = _mock_redis()


@pytest.fixture(autouse=True)
def _patch_redis():
    targets = [
        "app.extensions.redis_client",
        "app.routes.auth.redis_client",
        "app.services.cache.redis_client",
    ]
    patchers = [patch(t, _REDIS_MOCK) for t in targets]
    for p in patchers:
        p.start()
    yield
    for p in patchers:
        p.stop()


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
