import os
import sys
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("FLASK_ENV", "testing")

# Create a comprehensive mock redis client
_mock_redis = MagicMock()
_mock_redis.flushdb = MagicMock()
_mock_redis.get = MagicMock(return_value=None)
_mock_redis.setex = MagicMock()
_mock_redis.delete = MagicMock()
_mock_redis.pipeline = MagicMock(return_value=MagicMock())
_mock_redis.scan_iter = MagicMock(return_value=[])
_mock_redis.scan = MagicMock(return_value=(0, []))  # (cursor, keys) tuple

# Patch redis.Redis.from_url BEFORE any app module is imported
_redis_patcher = patch("redis.Redis.from_url", return_value=_mock_redis)
_redis_patcher.start()

from app import create_app
from app.config import Settings
from app.extensions import db
from app import models  # noqa: F401

# Ensure module-level redis_client references point to our mock
import app.extensions
import app.routes.auth as auth_mod
import app.services.cache as cache_mod

app.extensions.redis_client = _mock_redis
if hasattr(auth_mod, "redis_client"):
    auth_mod.redis_client = _mock_redis
if hasattr(cache_mod, "redis_client"):
    cache_mod.redis_client = _mock_redis


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret"


def _setup_db(app):
    with app.app_context():
        db.create_all()


@pytest.fixture()
def app_fixture():
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
