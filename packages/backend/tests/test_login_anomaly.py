"""Tests for login anomaly detection & suspicious activity alerts."""

import pytest
from datetime import datetime, timedelta
from app.services.login_anomaly import (
    record_login, get_login_history, get_alerts,
    acknowledge_alert, get_security_summary,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


@pytest.fixture
def login_history(app, user):
    """Seed some normal login history."""
    with app.app_context():
        for i in range(10):
            record_login(user, "192.168.1.1", "Mozilla/5.0", "US", "New York")
        return user


class TestRecordLogin:
    def test_first_login(self, app, user):
        with app.app_context():
            result = record_login(user, "10.0.0.1")
            assert result["login_id"] > 0
            assert result["anomaly_score"] == 0  # no history = no anomaly

    def test_normal_login(self, app, login_history):
        with app.app_context():
            result = record_login(login_history, "192.168.1.1", "Mozilla/5.0", "US", "New York")
            assert result["anomaly_score"] == 0

    def test_new_ip(self, app, login_history):
        with app.app_context():
            result = record_login(login_history, "10.99.99.99", "Mozilla/5.0", "US", "New York")
            assert result["anomaly_score"] > 0
            assert "new_ip" in result["anomaly_reasons"]

    def test_new_country(self, app, login_history):
        with app.app_context():
            result = record_login(login_history, "10.0.0.1", "Mozilla/5.0", "RU", "Moscow")
            assert "new_country" in result["anomaly_reasons"]
            assert result["anomaly_score"] >= 40

    def test_brute_force(self, app, login_history):
        with app.app_context():
            for _ in range(5):
                record_login(login_history, "192.168.1.1", success=False)
            result = record_login(login_history, "192.168.1.1", success=False)
            assert "brute_force" in result["anomaly_reasons"]

    def test_alerts_created(self, app, login_history):
        with app.app_context():
            result = record_login(login_history, "10.0.0.1", country="CN", city="Beijing")
            assert len(result["alerts"]) > 0


class TestLoginHistory:
    def test_empty(self, app, user):
        with app.app_context():
            h = get_login_history(user)
            assert h == []

    def test_with_data(self, app, login_history):
        with app.app_context():
            h = get_login_history(login_history)
            assert len(h) == 10

    def test_limit(self, app, login_history):
        with app.app_context():
            h = get_login_history(login_history, limit=3)
            assert len(h) == 3


class TestAlerts:
    def test_empty(self, app, user):
        with app.app_context():
            assert get_alerts(user) == []

    def test_with_anomaly(self, app, login_history):
        with app.app_context():
            record_login(login_history, "10.0.0.1", country="RU")
            alerts = get_alerts(login_history)
            assert len(alerts) > 0

    def test_unacknowledged_filter(self, app, login_history):
        with app.app_context():
            record_login(login_history, "10.0.0.1", country="RU")
            alerts = get_alerts(login_history, unacknowledged_only=True)
            assert all(not a["acknowledged"] for a in alerts)

    def test_acknowledge(self, app, login_history):
        with app.app_context():
            record_login(login_history, "10.0.0.1", country="RU")
            alerts = get_alerts(login_history)
            assert acknowledge_alert(login_history, alerts[0]["id"]) is True
            unack = get_alerts(login_history, unacknowledged_only=True)
            assert len(unack) < len(alerts)

    def test_acknowledge_not_found(self, app, user):
        with app.app_context():
            assert acknowledge_alert(user, 9999) is False


class TestSecuritySummary:
    def test_empty(self, app, user):
        with app.app_context():
            s = get_security_summary(user)
            assert s["total_logins"] == 0
            assert s["risk_level"] == "low"

    def test_normal(self, app, login_history):
        with app.app_context():
            s = get_security_summary(login_history)
            assert s["total_logins"] == 10
            assert s["risk_level"] == "low"

    def test_high_risk(self, app, login_history):
        with app.app_context():
            for _ in range(10):
                record_login(login_history, "10.0.0.1", success=False)
            s = get_security_summary(login_history)
            assert s["risk_level"] in ("medium", "high")


class TestAPI:
    def test_record(self, app, user, token):
        client = app.test_client()
        resp = client.post("/security/login-event",
                           json={"ip_address": "10.0.0.1", "country": "US"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_history(self, app, login_history, token):
        client = app.test_client()
        resp = client.get("/security/login-history",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_alerts(self, app, user, token):
        client = app.test_client()
        resp = client.get("/security/alerts",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_summary(self, app, user, token):
        client = app.test_client()
        resp = client.get("/security/summary",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "risk_level" in resp.get_json()
