from datetime import datetime, timedelta


def test_record_login_attempt_creates_entry(app_fixture):
    from app.extensions import db
    from app.models import LoginAttempt, User
    from app.services.anomaly_detection import record_login_attempt

    with app_fixture.app_context():
        user = User(email="anomaly@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        attempt = record_login_attempt(
            email=user.email, success=True,
            ip_address="1.2.3.4", user_agent="Chrome/1",
            user_id=user.id,
        )
        assert attempt.id is not None
        assert attempt.success is True
        assert attempt.ip_address == "1.2.3.4"


def test_rapid_attempts_detected(app_fixture):
    from app.extensions import db
    from app.models import LoginAttempt, LoginAttemptLevel, User
    from app.services.anomaly_detection import record_login_attempt

    with app_fixture.app_context():
        user = User(email="rapid@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        for _ in range(6):
            record_login_attempt(
                email=user.email, success=True,
                ip_address="5.6.7.8", user_agent="FF/1",
                user_id=user.id,
            )

        recent = (
            db.session.query(LoginAttempt)
            .filter(
                LoginAttempt.user_id == user.id,
                LoginAttempt.level == LoginAttemptLevel.SUSPICIOUS,
            )
            .count()
        )
        assert recent >= 1


def test_new_location_detected(app_fixture):
    from app.extensions import db
    from app.models import LoginAttempt, LoginAttemptLevel, User
    from app.services.anomaly_detection import record_login_attempt

    with app_fixture.app_context():
        user = User(email="location@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        record_login_attempt(
            email=user.email, success=True,
            ip_address="10.0.0.1", user_agent="Chrome/1",
            user_id=user.id,
        )

        attempt2 = record_login_attempt(
            email=user.email, success=True,
            ip_address="10.0.0.2", user_agent="Chrome/1",
            user_id=user.id,
        )
        assert attempt2.level == LoginAttemptLevel.SUSPICIOUS


def test_unusual_time_detected(app_fixture):
    from datetime import datetime as dt
    from app.extensions import db
    from app.models import LoginAttempt, LoginAttemptLevel, User
    from app.services.anomaly_detection import _detect_unusual_time

    with app_fixture.app_context():
        user = User(email="time@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        daytime = LoginAttempt(
            user_id=user.id, email=user.email, success=True,
            ip_address="1.2.3.4", created_at=dt(2026, 5, 30, 12, 0, 0),
        )
        db.session.add(daytime)
        db.session.commit()

        late = LoginAttempt(
            user_id=user.id, email=user.email, success=True,
            ip_address="1.2.3.4", created_at=dt(2026, 5, 30, 3, 0, 0),
        )
        result = _detect_unusual_time(user.id, late)
        assert result is not None
        assert result["type"] == "unusual_time"
        assert result["severity"] == "low"


def test_list_alerts_endpoint(client, auth_header):
    r = client.get("/anomaly/alerts", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_login_history_endpoint(client, auth_header):
    r = client.get("/anomaly/login-history", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()
    assert isinstance(history, list)
    assert len(history) >= 1
    assert history[0]["success"] is True


def test_acknowledge_alert(client, auth_header):
    r = client.get("/anomaly/alerts", headers=auth_header)
    alerts = r.get_json()
    if alerts:
        alert_id = alerts[0]["id"]
        r = client.post(f"/anomaly/alerts/{alert_id}/acknowledge", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["message"] == "acknowledged"


def test_acknowledge_nonexistent_alert_returns_404(client, auth_header):
    r = client.post("/anomaly/alerts/99999/acknowledge", headers=auth_header)
    assert r.status_code == 404
