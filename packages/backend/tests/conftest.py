import os
from unittest.mock import patch

import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app.extensions import redis_client
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret"


class _FakeRedis:
    def __init__(self):
        self._data: dict[str, str] = {}

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value

    def set(self, key, value, **kw):
        self._data[key] = value

    def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)

    def flushdb(self):
        self._data.clear()

    def scan(self, cursor=0, match=None, count=100):
        import fnmatch
        keys = list(self._data.keys())
        if match:
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        return (0, keys)


_PATCH_TARGETS = [
    "app.routes.auth",
    "app.services.cache",
]


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
    try:
        redis_client.flushdb()
    except Exception:
        pass
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        redis_client.flushdb()
    except Exception:
        pass


@pytest.fixture()
def client(app_fixture):
    fake = _FakeRedis()
    patchers = [patch(f"{t}.redis_client", fake) for t in _PATCH_TARGETS]
    for p in patchers:
        p.start()
    yield app_fixture.test_client()
    for p in patchers:
        p.stop()


@pytest.fixture()
def auth_header(client):
    email = "test@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    register_debug = f"register failed: status={r.status_code}, body={r.get_json()}"
    assert r.status_code in (200, 201, 409), register_debug
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}
