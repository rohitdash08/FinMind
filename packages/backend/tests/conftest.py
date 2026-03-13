import os
import pytest
import fakeredis
from app import create_app
from app.config import Settings
from app.extensions import db
from app.extensions import redis_client as real_redis_client
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    # Override defaults for tests
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"  # not used in tests
    jwt_secret: str = "test-secret"


def _setup_db(app):
    with app.app_context():
        db.create_all()


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.extensions.redis_client", fake)
    monkeypatch.setattr("app.routes.auth.redis_client", fake)
    monkeypatch.setattr("app.services.cache.redis_client", fake)
    # Also patch where it might be imported directly in my new code
    monkeypatch.setattr("app.routes.insights.cache_get", lambda k: fake.get(k))
    monkeypatch.setattr("app.routes.insights.cache_set", lambda k, v, ttl_seconds=None: fake.setex(k, ttl_seconds, v) if ttl_seconds else fake.set(k, v))
    return fake


@pytest.fixture()
def app_fixture(mock_redis):
    # Ensure a clean env for tests
    os.environ.setdefault("FLASK_ENV", "testing")
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    app = create_app(settings)
    app.config.update(TESTING=True)
    _setup_db(app)
    mock_redis.flushdb()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    mock_redis.flushdb()


@pytest.fixture()
def client(app_fixture):
    return app_fixture.test_client()


@pytest.fixture()
def auth_header(client):
    # Register and login a default user, return auth header
    email = "test@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    register_debug = f"register failed: status={r.status_code}, body={r.get_json()}"
    assert r.status_code in (
        200,
        201,
        409,
    ), register_debug  # 409 if already exists
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}
