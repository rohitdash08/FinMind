import os
import sys
import pytest

# Patch Redis BEFORE any app imports happen
import fakeredis
import redis

_original_from_url = redis.Redis.from_url

def _fake_from_url(cls, url, **kwargs):
    # Return FakeRedis for any test Redis URL
    decode = kwargs.get('decode_responses', False)
    return fakeredis.FakeRedis(decode_responses=decode)

redis.Redis.from_url = classmethod(_fake_from_url)

# Now import the app
from app import create_app
from app.config import Settings
from app.extensions import db, redis_client
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-with-32-plus-chars-1234567890"


@pytest.fixture()
def app_fixture():
    os.environ.setdefault("FLASK_ENV", "testing")
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    app = create_app(settings)
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
    yield app
    try:
        redis_client.flushdb()
    except Exception:
        pass


@pytest.fixture()
def client(app_fixture):
    return app_fixture.test_client()


@pytest.fixture()
def auth_header(client):
    email = "test@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    register_debug = f"register failed: status={r.status_code}, body={r.get_json()}"
    assert r.status_code in (200, 201, 409), register_debug
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}
