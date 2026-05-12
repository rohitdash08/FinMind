import os
import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app import models  # noqa: F401 - ensure models are registered


class InMemoryRedis:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value
        return True

    def setex(self, key, _ttl, value):
        self._data[key] = value
        return True

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self._data:
                deleted += 1
                del self._data[key]
        return deleted

    def flushdb(self):
        self._data.clear()
        return True

    def scan(self, cursor=0, match=None, count=100):
        import fnmatch

        keys = list(self._data)
        if match:
            keys = [key for key in keys if fnmatch.fnmatch(key, match)]
        return 0, keys[:count]


def _install_test_redis():
    fake = InMemoryRedis()
    import app.extensions as extensions
    import app.routes.auth as auth
    import app.services.cache as cache

    extensions.redis_client = fake
    auth.redis_client = fake
    cache.redis_client = fake
    return fake


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
    fake_redis = _install_test_redis()
    app = create_app(settings)
    app.config.update(TESTING=True)
    _setup_db(app)
    try:
        fake_redis.flushdb()
    except Exception:
        pass
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        fake_redis.flushdb()
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
