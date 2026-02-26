"""Tests for login anomaly detection & suspicious activity alerts (#124)."""

import json
from datetime import datetime, timezone


def _register_and_login(client, email="anomaly@test.com", password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    return data["access_token"], data.get("refresh_token")


def test_login_records_event(client, app_fixture):
    """Successful login should create a LoginEvent row."""
    from app.models import LoginEvent

    _register_and_login(client)
    with app_fixture.app_context():
        events = LoginEvent.query.all()
        assert len(events) >= 1
        assert events[0].success is True


def test_failed_login_records_event(client, app_fixture):
    """Failed login should record an event when user exists."""
    from app.models import LoginEvent

    client.post(
        "/auth/register",
        json={"email": "fail@test.com", "password": "secret123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "fail@test.com", "password": "wrong"},
    )
    assert r.status_code == 401
    with app_fixture.app_context():
        events = LoginEvent.query.filter_by(success=False).all()
        assert len(events) >= 1


def test_new_ip_alert(client, app_fixture):
    """Login from a new IP should generate a new_ip alert."""
    from app.models import SecurityAlert

    email, pw = "iptest@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    # First login — establishes baseline
    client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )

    # Second login from different IP
    r = client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"X-Forwarded-For": "5.6.7.8"},
    )
    assert r.status_code == 200
    data = r.get_json()

    with app_fixture.app_context():
        alerts = SecurityAlert.query.filter_by(alert_type="new_ip").all()
        assert len(alerts) >= 1
        assert "5.6.7.8" in alerts[-1].message


def test_new_device_alert(client, app_fixture):
    """Login from a new device fingerprint should generate a new_device alert."""
    from app.models import SecurityAlert

    email, pw = "devtest@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    # First login with one user-agent
    client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
    )

    # Second login with different user-agent
    r = client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"User-Agent": "Mozilla/5.0 Firefox/121"},
    )
    assert r.status_code == 200

    with app_fixture.app_context():
        alerts = SecurityAlert.query.filter_by(alert_type="new_device").all()
        assert len(alerts) >= 1


def test_security_alerts_endpoint(client):
    """GET /auth/security-alerts returns alerts for the user."""
    access, _ = _register_and_login(client, "alerts@test.com", "secret123")
    auth = {"Authorization": f"Bearer {access}"}

    # Login from new IP to trigger alert
    client.post(
        "/auth/login",
        json={"email": "alerts@test.com", "password": "secret123"},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )

    r = client.get("/auth/security-alerts", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


def test_acknowledge_alert(client, app_fixture):
    """POST /auth/security-alerts/<id>/acknowledge marks alert as read."""
    from app.models import SecurityAlert

    email, pw = "ack@test.com", "secret123"
    client.post("/auth/register", json={"email": email, "password": pw})

    # First login
    client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"X-Forwarded-For": "1.1.1.1"},
    )
    # Second login from new IP to trigger alert
    r = client.post(
        "/auth/login",
        json={"email": email, "password": pw},
        headers={"X-Forwarded-For": "2.2.2.2"},
    )
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    with app_fixture.app_context():
        alert = SecurityAlert.query.first()
        if alert:
            alert_id = alert.id
            r = client.post(
                f"/auth/security-alerts/{alert_id}/acknowledge",
                headers=auth,
            )
            assert r.status_code == 200
            db_alert = SecurityAlert.query.get(alert_id)
            assert db_alert.acknowledged is True


def test_acknowledge_nonexistent_alert(client):
    """Acknowledging a non-existent alert returns 404."""
    access, _ = _register_and_login(client, "noalert@test.com", "secret123")
    auth = {"Authorization": f"Bearer {access}"}
    r = client.post("/auth/security-alerts/99999/acknowledge", headers=auth)
    assert r.status_code == 404
