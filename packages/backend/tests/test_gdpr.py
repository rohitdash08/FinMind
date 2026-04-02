import pytest
import os
import fakeredis
from app import create_app
from app.config import Settings
from app.extensions import db, init_redis
from app import models


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-with-32-plus-chars"


@pytest.fixture()
def gdpr_app():
    os.environ.setdefault("FLASK_ENV", "testing")
    
    # Use fakeredis for testing
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    
    settings = TestSettings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    
    app = create_app(settings)
    app.config.update(TESTING=True)
    
    # Override Redis with fake instance
    from app.extensions import _redis_client
    import app.extensions as ext
    ext._redis_client = fake_redis
    
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def gdpr_client(gdpr_app):
    return gdpr_app.test_client()


@pytest.fixture()
def gdpr_auth_header(gdpr_client):
    email = "gdpr_test@example.com"
    password = "password123"
    gdpr_client.post("/auth/register", json={"email": email, "password": password})
    r = gdpr_client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


def test_gdpr_export_returns_zip(gdpr_client, gdpr_auth_header):
    r = gdpr_client.get("/gdpr/export", headers=gdpr_auth_header)
    assert r.status_code == 200
    assert r.content_type == "application/zip"
    assert len(r.data) > 0


def test_gdpr_delete_request_creates_request(gdpr_client, gdpr_auth_header):
    r = gdpr_client.post("/gdpr/delete-request", headers=gdpr_auth_header)
    assert r.status_code == 202
    data = r.get_json()
    assert "scheduled_deletion_date" in data
    assert data["grace_period_days"] == 30


def test_gdpr_delete_request_rejects_duplicate(gdpr_client, gdpr_auth_header):
    r1 = gdpr_client.post("/gdpr/delete-request", headers=gdpr_auth_header)
    assert r1.status_code == 202
    r2 = gdpr_client.post("/gdpr/delete-request", headers=gdpr_auth_header)
    assert r2.status_code == 409


def test_gdpr_cancel_delete_request(gdpr_client, gdpr_auth_header):
    gdpr_client.post("/gdpr/delete-request", headers=gdpr_auth_header)
    r = gdpr_client.delete("/gdpr/delete-request", headers=gdpr_auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deletion request cancelled"


def test_gdpr_status_no_pending(gdpr_client, gdpr_auth_header):
    r = gdpr_client.get("/gdpr/status", headers=gdpr_auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["has_pending_deletion"] == False


def test_gdpr_status_with_pending(gdpr_client, gdpr_auth_header):
    gdpr_client.post("/gdpr/delete-request", headers=gdpr_auth_header)
    r = gdpr_client.get("/gdpr/status", headers=gdpr_auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["has_pending_deletion"] == True
    assert "days_remaining" in data


def test_gdpr_immediate_delete_requires_confirmation(gdpr_client, gdpr_auth_header):
    r = gdpr_client.delete("/gdpr/delete", headers=gdpr_auth_header, json={})
    assert r.status_code == 400
    assert "confirmation required" in r.get_json()["error"]


def test_gdpr_immediate_delete_with_confirmation(gdpr_client, gdpr_auth_header):
    r = gdpr_client.delete("/gdpr/delete", headers=gdpr_auth_header, json={"confirm": "DELETE_MY_ACCOUNT"})
    assert r.status_code == 200
    data = r.get_json()
    assert "account permanently deleted" in data["message"]
    assert "details" in data


def test_gdpr_delete_removes_user(gdpr_client):
    email = "delete_test@example.com"
    password = "password123"
    gdpr_client.post("/auth/register", json={"email": email, "password": password})
    r = gdpr_client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}
    
    r = gdpr_client.delete("/gdpr/delete", headers=auth, json={"confirm": "DELETE_MY_ACCOUNT"})
    assert r.status_code == 200
    
    # Verify user can no longer login
    r = gdpr_client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401