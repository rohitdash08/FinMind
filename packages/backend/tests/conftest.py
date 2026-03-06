import os
import pytest
from unittest.mock import patch
import fakeredis

from app import create_app
from app.config import Settings
from app.extensions import db
from app import models  # noqa: F401 - ensure models are registered


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
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
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    with patch("app.extensions.redis_client", fake_redis), \
         patch("app.routes.auth.redis_client", fake_redis), \
         patch("app.services.cache.redis_client", fake_redis):
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
    email = "test@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    register_debug = f"register failed: status={r.status_code}, body={r.get_json()}"
    assert r.status_code in (200, 201, 409), register_debug
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}
