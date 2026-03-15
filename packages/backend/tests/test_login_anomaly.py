from datetime import datetime, timedelta
from unittest.mock import patch
from app.models import LoginAttempt
from app.extensions import db


def _register_and_login(client, email="anomaly@test.com", password="secret123"):
    """Register a user and login, returning (access_token, user_id)."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    # Decode user id from the token by hitting /auth/me
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    uid = r.get_json()["id"]
    return access, uid


def test_login_records_attempt(client, app_fixture):
    """Login should create a LoginAttempt record."""
    email = "record@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    client.post("/auth/login", json={"email": email, "password": password})

    with app_fixture.app_context():
        attempts = db.session.query(LoginAttempt).all()
        assert len(attempts) >= 1
        last = attempts[-1]
        assert last.success is True
        assert last.ip_address is not None


def test_failed_login_records_attempt(client, app_fixture):
    """Failed login should record an attempt if user exists."""
    email = "fail@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    client.post("/auth/login", json={"email": email, "password": "wrongpass"})

    with app_fixture.app_context():
        attempts = (
            db.session.query(LoginAttempt).filter_by(success=False).all()
        )
        assert len(attempts) >= 1


def test_new_ip_detection(client, app_fixture):
    """First login from a new IP should be flagged as new_ip anomaly."""
    email = "newip@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    # First login — always new IP
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200

    with app_fixture.app_context():
        attempt = (
            db.session.query(LoginAttempt)
            .filter_by(success=True)
            .order_by(LoginAttempt.id.desc())
            .first()
        )
        # First login should detect new_ip
        assert attempt.anomaly_type is not None
        assert "new_ip" in attempt.anomaly_type


def test_new_device_detection(client, app_fixture):
    """Login with a new user agent should be flagged."""
    email = "newdevice@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login with one UA
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "Mozilla/5.0 Chrome"},
    )
    assert r.status_code == 200

    # Second login with different UA
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "Mozilla/5.0 Firefox"},
    )
    assert r.status_code == 200

    with app_fixture.app_context():
        attempt = (
            db.session.query(LoginAttempt)
            .filter_by(success=True)
            .order_by(LoginAttempt.id.desc())
            .first()
        )
        assert attempt.anomaly_type is not None
        assert "new_device" in attempt.anomaly_type


def test_rapid_attempt_detection(client, app_fixture):
    """Rapid logins should be flagged after threshold."""
    email = "rapid@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Make 6 rapid login attempts (threshold is 5)
    for _ in range(6):
        client.post("/auth/login", json={"email": email, "password": password})

    with app_fixture.app_context():
        attempts = (
            db.session.query(LoginAttempt)
            .filter_by(success=True)
            .order_by(LoginAttempt.id.desc())
            .all()
        )
        # At least one should have rapid_attempts anomaly
        rapid = [a for a in attempts if a.anomaly_type and "rapid_attempts" in a.anomaly_type]
        assert len(rapid) >= 1


def test_login_history_endpoint(client):
    """GET /auth/login-history returns paginated login attempts."""
    access, _ = _register_and_login(client, "history@test.com", "secret123")
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/login-history", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "per_page" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1
    # Check item structure
    item = data["items"][0]
    assert "ip_address" in item
    assert "timestamp" in item
    assert "success" in item
    assert "suspicious" in item


def test_login_history_pagination(client):
    """Login history supports pagination parameters."""
    access, _ = _register_and_login(client, "paginate@test.com", "secret123")
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/login-history?page=1&per_page=5", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 5


def test_suspicious_alerts_endpoint(client, app_fixture):
    """GET /auth/suspicious-alerts returns only suspicious login attempts."""
    email = "suspicious@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login is always from new IP/device, so it should be suspicious
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/suspicious-alerts", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert "total" in data
    # All returned items should be suspicious
    for item in data["items"]:
        assert "anomaly_type" in item


def test_login_history_requires_auth(client):
    """Login history endpoint requires authentication."""
    r = client.get("/auth/login-history")
    assert r.status_code == 401


def test_suspicious_alerts_requires_auth(client):
    """Suspicious alerts endpoint requires authentication."""
    r = client.get("/auth/suspicious-alerts")
    assert r.status_code == 401
