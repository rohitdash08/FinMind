from datetime import datetime, timedelta
from app.models import LoginEvent, LoginAnomaly
from app.extensions import db


def _register_and_login(client, email="security@test.com", password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    return data["access_token"], data.get("refresh_token")


def test_login_records_event(client, app_fixture):
    email = "event@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    client.post("/auth/login", json={"email": email, "password": password})

    with app_fixture.app_context():
        events = db.session.query(LoginEvent).filter_by(email=email).all()
        assert len(events) >= 1
        assert events[-1].success is True


def test_failed_login_records_event(client, app_fixture):
    email = "fail@test.com"
    client.post("/auth/register", json={"email": email, "password": "correct"})
    client.post("/auth/login", json={"email": email, "password": "wrong"})

    with app_fixture.app_context():
        events = (
            db.session.query(LoginEvent)
            .filter_by(email=email, success=False)
            .all()
        )
        assert len(events) >= 1


def test_new_ip_anomaly_detection(client, app_fixture):
    email = "newip@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login establishes baseline
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "1.1.1.1"},
    )

    with app_fixture.app_context():
        # Manually set the IP on the first event to simulate different IPs
        event = db.session.query(LoginEvent).filter_by(email=email).first()
        event.ip_address = "1.1.1.1"
        db.session.commit()

    # Second login from same IP - no anomaly
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )

    # Third login - manually set different IP to trigger detection
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )

    with app_fixture.app_context():
        # Simulate: set the last event to a different IP for the test
        events = (
            db.session.query(LoginEvent)
            .filter_by(email=email, success=True)
            .all()
        )
        if len(events) >= 2:
            # Make first event use different IP than later ones
            events[0].ip_address = "10.0.0.1"
            db.session.commit()

            # Now re-run detection manually
            from app.services.login_anomaly import _check_new_ip

            user = db.session.query(LoginEvent).filter_by(email=email).first()
            _check_new_ip(events[-1], events[-1].user_id)
            db.session.commit()

            anomalies = (
                db.session.query(LoginAnomaly)
                .filter_by(anomaly_type="NEW_IP")
                .all()
            )
            assert len(anomalies) >= 1


def test_brute_force_detection(client, app_fixture):
    email = "brute@test.com"
    password = "correct"
    client.post("/auth/register", json={"email": email, "password": password})

    # Attempt 5+ failed logins
    for _ in range(6):
        client.post("/auth/login", json={"email": email, "password": "wrong"})

    with app_fixture.app_context():
        anomalies = (
            db.session.query(LoginAnomaly)
            .filter_by(anomaly_type="BRUTE_FORCE")
            .all()
        )
        assert len(anomalies) >= 1
        assert anomalies[0].severity == "HIGH"


def test_login_history_endpoint(client, app_fixture):
    access, _ = _register_and_login(client)
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/security/login-history", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "events" in data
    assert len(data["events"]) >= 1
    assert "ip_address" in data["events"][0]
    assert "success" in data["events"][0]


def test_anomalies_endpoint(client, app_fixture):
    access, _ = _register_and_login(client)
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/security/anomalies", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "anomalies" in data


def test_acknowledge_anomaly(client, app_fixture):
    email = "ack@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Create a login to get user_id
    r = client.post("/auth/login", json={"email": email, "password": password})
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    # Manually create an anomaly
    with app_fixture.app_context():
        user = db.session.query(LoginEvent).filter_by(email=email).first()
        anomaly = LoginAnomaly(
            user_id=user.user_id,
            anomaly_type="NEW_IP",
            severity="MEDIUM",
            details="Test anomaly",
        )
        db.session.add(anomaly)
        db.session.commit()
        anomaly_id = anomaly.id

    r = client.post(f"/security/anomalies/{anomaly_id}/acknowledge", headers=auth)
    assert r.status_code == 200

    # Verify it's acknowledged
    r = client.get("/security/anomalies?unacknowledged_only=true", headers=auth)
    data = r.get_json()
    ack_ids = [a["id"] for a in data["anomalies"]]
    assert anomaly_id not in ack_ids


def test_acknowledge_nonexistent_anomaly(client, app_fixture):
    access, _ = _register_and_login(client)
    auth = {"Authorization": f"Bearer {access}"}
    r = client.post("/security/anomalies/99999/acknowledge", headers=auth)
    assert r.status_code == 404


def test_login_history_requires_auth(client):
    r = client.get("/security/login-history")
    assert r.status_code == 401


def test_odd_hour_anomaly(client, app_fixture):
    email = "oddhour@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    client.post("/auth/login", json={"email": email, "password": password})

    with app_fixture.app_context():
        # Manually set login time to 3 AM UTC
        event = (
            db.session.query(LoginEvent)
            .filter_by(email=email, success=True)
            .first()
        )
        event.created_at = datetime.utcnow().replace(hour=3, minute=0)
        db.session.commit()

        # Re-run odd hour check
        from app.services.login_anomaly import _check_odd_hour

        _check_odd_hour(event, event.user_id)
        db.session.commit()

        anomalies = (
            db.session.query(LoginAnomaly)
            .filter_by(anomaly_type="ODD_HOUR")
            .all()
        )
        assert len(anomalies) >= 1
