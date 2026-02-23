import os
from unittest.mock import MagicMock
import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
import app.extensions as extensions
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    # Override defaults for tests
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"  # not used in tests
    jwt_secret: str = "test-secret"


def _redis_available():
    try:
        extensions.redis_client.ping()
        return True
    except Exception:
        return False


def _setup_db(app):
    with app.app_context():
        db.create_all()


@pytest.fixture()
def app_fixture():
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

    # Mock Redis if not available to allow tests to run without Docker
    if not _redis_available():
        mock_redis = MagicMock()
        mock_redis.get.return_value = "1"
        mock_redis.setex.return_value = True
        mock_redis.delete.return_value = True
        mock_redis.flushdb.return_value = True
        extensions.redis_client = mock_redis
        # Also patch in auth module which imports redis_client by name
        import app.routes.auth as auth_mod
        auth_mod.redis_client = mock_redis
    else:
        try:
            extensions.redis_client.flushdb()
        except Exception:
            pass

    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        extensions.redis_client.flushdb()
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
