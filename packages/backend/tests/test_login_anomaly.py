import json
from datetime import datetime, timedelta
from app.extensions import db
from app.models import LoginEvent


def _register_and_login(client, app_fixture, email="security@test.com", password="secret123"):
    """Register a user and login, return (access_token, user_id)."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    with app_fixture.app_context():
        from app.models import User
        user = db.session.query(User).filter_by(email=email).first()
        uid = user.id
    return data["access_token"], uid


def test_login_records_event(client, app_fixture):
    """Login should create a LoginEvent record."""
    with app_fixture.app_context():
        assert db.session.query(LoginEvent).count() == 0

    _register_and_login(client, app_fixture)

    with app_fixture.app_context():
        events = db.session.query(LoginEvent).all()
        assert len(events) >= 1
        latest = events[-1]
        assert latest.success is True


def test_new_ip_detected(client, app_fixture):
    """First login from an IP should flag new_ip."""
    access, uid = _register_and_login(client, app_fixture)

    with app_fixture.app_context():
        event = (
            db.session.query(LoginEvent)
            .filter_by(user_id=uid, success=True)
            .order_by(LoginEvent.id.desc())
            .first()
        )
        assert event is not None
        reasons = json.loads(event.anomaly_reasons) if event.anomaly_reasons else []
        assert "new_ip" in reasons


def test_new_device_detected(client, app_fixture):
    """First login from a device should flag new_device."""
    access, uid = _register_and_login(client, app_fixture)

    with app_fixture.app_context():
        event = (
            db.session.query(LoginEvent)
            .filter_by(user_id=uid, success=True)
            .order_by(LoginEvent.id.desc())
            .first()
        )
        assert event is not None
        reasons = json.loads(event.anomaly_reasons) if event.anomaly_reasons else []
        assert "new_device" in reasons


def test_brute_force_detected(client, app_fixture):
    """5+ failed logins in 15 min should flag brute_force."""
    email = "brute@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Make 5 failed login attempts
    for _ in range(5):
        client.post("/auth/login", json={"email": email, "password": "wrong"})

    # 6th attempt should detect brute force
    client.post("/auth/login", json={"email": email, "password": "wrong"})

    with app_fixture.app_context():
        events = (
            db.session.query(LoginEvent)
            .filter_by(success=False)
            .order_by(LoginEvent.id.desc())
            .all()
        )
        latest = events[0]
        reasons = json.loads(latest.anomaly_reasons) if latest.anomaly_reasons else []
        assert "brute_force" in reasons


def test_odd_hour_detected(app_fixture):
    """Login between 2-5 AM UTC should flag odd_hour."""
    from app.services.login_anomaly import _check_odd_hours

    assert _check_odd_hours(datetime(2026, 1, 1, 3, 0)) is True
    assert _check_odd_hours(datetime(2026, 1, 1, 2, 0)) is True
    assert _check_odd_hours(datetime(2026, 1, 1, 4, 59)) is True
    assert _check_odd_hours(datetime(2026, 1, 1, 5, 0)) is False
    assert _check_odd_hours(datetime(2026, 1, 1, 12, 0)) is False
    assert _check_odd_hours(datetime(2026, 1, 1, 1, 59)) is False


def test_login_history_endpoint(client, auth_header):
    """GET /security/login-history returns recent logins."""
    r = client.get("/security/login-history", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert len(data["events"]) >= 1


def test_anomalies_endpoint(client, auth_header):
    """GET /security/anomalies returns anomalous events."""
    r = client.get("/security/anomalies", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "anomalies" in data
    assert isinstance(data["anomalies"], list)


def test_login_stats_endpoint(client, auth_header):
    """GET /security/login-stats returns summary stats."""
    r = client.get("/security/login-stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "unique_ips" in data
    assert "unique_devices" in data
    assert "total_logins" in data


def test_security_requires_auth(client):
    """Security endpoints should require JWT auth."""
    for path in ["/security/login-history", "/security/anomalies", "/security/login-stats"]:
        r = client.get(path)
        assert r.status_code == 401


def test_normal_login_no_anomaly(client, app_fixture):
    """Second login from same IP/device should have score 0."""
    email = "repeat@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login (will have new_ip + new_device)
    client.post("/auth/login", json={"email": email, "password": password})

    # Second login from same IP/device
    client.post("/auth/login", json={"email": email, "password": password})

    with app_fixture.app_context():
        from app.models import User
        user = db.session.query(User).filter_by(email=email).first()
        events = (
            db.session.query(LoginEvent)
            .filter_by(user_id=user.id, success=True)
            .order_by(LoginEvent.id.desc())
            .all()
        )
        latest = events[0]
        assert latest.anomaly_score == 0.0
