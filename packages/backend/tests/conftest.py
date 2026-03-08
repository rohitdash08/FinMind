import os
import pytest
import fakeredis
from unittest.mock import patch
from app import create_app
from app.config import Settings
from app.extensions import db
from app.extensions import redis_client
from app import models  # noqa: F401 - ensure models are registered

# Patch redis_client globally with fakeredis for tests
_fake_redis = fakeredis.FakeRedis(decode_responses=True)

@pytest.fixture(autouse=True)
def _patch_redis():
    import app.extensions as ext
    import app.routes.auth as auth_mod
    import app.routes.gdpr as gdpr_mod
    import app.services.cache as cache_mod
    old = {
        'ext': ext.redis_client,
        'auth': auth_mod.redis_client,
        'gdpr': gdpr_mod.redis_client,
        'cache': cache_mod.redis_client,
    }
    ext.redis_client = _fake_redis
    auth_mod.redis_client = _fake_redis
    gdpr_mod.redis_client = _fake_redis
    cache_mod.redis_client = _fake_redis
    _fake_redis.flushdb()
    yield
    ext.redis_client = old['ext']
    auth_mod.redis_client = old['auth']
    gdpr_mod.redis_client = old['gdpr']
    cache_mod.redis_client = old['cache']


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
