import os
from unittest.mock import patch
import pytest
import redis as redis_module
from app import create_app
from app.config import Settings
from app.extensions import db
import app.models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret"


mock_redis_instance = redis_module.Redis.from_url("redis://localhost:6379", decode_responses=True)


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
    try:
        mock_redis_instance.flushdb()
    except Exception:
        pass
    app = create_app(settings)
    app.config.update(TESTING=True)
    _setup_db(app)
    import app.routes.auth as _auth_mod
    _auth_mod.redis_client = mock_redis_instance
    import app.extensions as _ext_mod
    _ext_mod.redis_client = mock_redis_instance
    import app.services.cache as _cache_mod
    _cache_mod.redis_client = mock_redis_instance

    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        mock_redis_instance.flushdb()
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
