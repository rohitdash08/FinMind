import os
import pytest
from app.config import Settings
from app.extensions import db
import fakeredis


# Patch redis_client with fakeredis when real Redis is unavailable.
# This must happen before importing create_app (which triggers route imports).
_faker = fakeredis.FakeRedis(decode_responses=True)
try:
    from app.extensions import redis_client
    redis_client.ping()
except Exception:
    import app.extensions as _ext
    _ext.redis_client = _faker
    # Patch all modules that imported redis_client at module level
    import app.routes.auth as _auth
    _auth.redis_client = _faker
    import app.services.cache as _cache
    _cache.redis_client = _faker

from app import create_app
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    # Override defaults for tests
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"  # not used in tests
    jwt_secret: str = "test-secret"


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
    _faker.flushdb()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    _faker.flushdb()


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
