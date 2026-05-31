import os
import pytest
import redis
from app import create_app
from app.config import Settings
from app.extensions import db
from app.extensions import redis_client as _orig_redis
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret"


def _setup_db(app):
    with app.app_context():
        db.create_all()


@pytest.fixture()
def app_fixture(monkeypatch):
    local_redis = redis.Redis.from_url("redis://localhost:6379/15", decode_responses=True)
    monkeypatch.setattr("app.extensions.redis_client", local_redis)
    monkeypatch.setattr("app.routes.auth.redis_client", local_redis)
    monkeypatch.setattr("app.services.cache.redis_client", local_redis)
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
        local_redis.flushdb()
    except Exception:
        pass
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        local_redis.flushdb()
    except Exception:
        pass


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
