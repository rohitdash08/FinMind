import os
import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app import models  # noqa: F401 - ensure models are registered


class FakeRedis:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[str(key)] = value

    def setex(self, key, _ttl, value):
        self.store[str(key)] = value

    def get(self, key):
        return self.store.get(str(key))

    def delete(self, *keys):
        for key in keys:
            self.store.pop(str(key), None)

    def scan(self, cursor=0, match=None, count=100):
        import fnmatch

        keys = list(self.store)
        if match:
            keys = [key for key in keys if fnmatch.fnmatch(key, match)]
        return 0, keys[:count]

    def flushdb(self):
        self.store.clear()


class TestSettings(Settings):
    # Override defaults for tests
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"  # not used in tests
    jwt_secret: str = "test-secret"


def _setup_db(app):
    with app.app_context():
        db.create_all()


def _patch_redis(fake_redis):
    import app.extensions as extensions
    import app.routes.auth as auth_route
    import app.services.cache as cache_service

    extensions.redis_client = fake_redis
    auth_route.redis_client = fake_redis
    cache_service.redis_client = fake_redis


@pytest.fixture()
def app_fixture():
    # Ensure a clean env for tests
    os.environ.setdefault("FLASK_ENV", "testing")
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    fake_redis = FakeRedis()
    _patch_redis(fake_redis)
    app = create_app(settings)
    app.config.update(TESTING=True)
    _setup_db(app)
    fake_redis.flushdb()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    fake_redis.flushdb()


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
