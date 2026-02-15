from app import create_app
from app.config import Settings
from app.extensions import db
import app.extensions as app_extensions


def test_auth_refresh_flow(client):
    # Register user
    email = "refresh@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)  # 409 if already exists

    # Login to get tokens
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data and "refresh_token" in data

    # Use refresh to get a new access token
    refresh_token = data["refresh_token"]
    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200
    new_access = r.get_json().get("access_token")
    assert isinstance(new_access, str) and len(new_access) > 10


def test_auth_logout_revokes_refresh_token(client):
    email = "logout@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    refresh_token = r.get_json()["refresh_token"]

    r = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 401


def test_auth_login_in_testing_mode_does_not_use_real_redis(monkeypatch):
    called = {"from_url": 0}

    def _raise_if_called(*args, **kwargs):
        called["from_url"] += 1
        raise AssertionError(
            "redis.Redis.from_url should not be called in TESTING mode"
        )

    monkeypatch.setattr(app_extensions.redis.Redis, "from_url", _raise_if_called)
    monkeypatch.setenv("FLASK_ENV", "testing")

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://redis:6379/0",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    app = create_app(settings)
    app.config.update(TESTING=True)

    with app.app_context():
        db.create_all()

    client = app.test_client()
    email = "no-redis@test.com"
    password = "secret123"
    register = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert register.status_code in (201, 409)

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    payload = login.get_json()
    assert isinstance(payload.get("refresh_token"), str)
    assert called["from_url"] == 0
