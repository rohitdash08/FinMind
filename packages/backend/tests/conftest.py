import os
import fakeredis
import pytest
import app.extensions as _ext
import app.routes.auth as _auth_route
import app.services.cache as _cache_svc
from app import create_app
from app.config import Settings
from app.extensions import db
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
    os.environ.setdefault("FLASK_ENV", "testing")
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    # Replace the real Redis client with fakeredis in every location where it
    # was imported by name.  The source singleton plus the two modules that did
    # `from ..extensions import redis_client` each hold their own reference.
    _real = _ext.redis_client
    fake = fakeredis.FakeRedis(decode_responses=True)
    _ext.redis_client = fake
    _auth_route.redis_client = fake
    _cache_svc.redis_client = fake

    app = create_app(settings)
    app.config.update(TESTING=True)
    _setup_db(app)
    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()
    fake.flushall()
    # Restore originals so other test sessions aren't affected
    _ext.redis_client = _real
    _auth_route.redis_client = _real
    _cache_svc.redis_client = _real


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
