import os
import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app import models  # noqa: F401 - ensure models are registered
from app import extensions
from app.routes import auth as auth_routes
from app.services import cache as cache_service


class InMemoryRedis:
    def __init__(self):
        self._data: dict[str, str] = {}

    def setex(self, key: str, _ttl: int, value: str):
        self._data[key] = value

    def set(self, key: str, value: str):
        self._data[key] = value

    def get(self, key: str):
        return self._data.get(key)

    def delete(self, *keys: str):
        for key in keys:
            self._data.pop(key, None)

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):
        del count
        if match is None:
            return 0, list(self._data.keys())
        prefix = match.rstrip("*")
        return 0, [key for key in self._data if key.startswith(prefix)]

    def flushdb(self):
        self._data.clear()


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
    redis_client = InMemoryRedis()
    extensions.redis_client = redis_client
    auth_routes.redis_client = redis_client
    cache_service.redis_client = redis_client
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
