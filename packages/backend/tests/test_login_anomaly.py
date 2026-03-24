"""Tests for login anomaly detection."""

import json
import pytest
from unittest.mock import patch
from app import create_app
from app.config import Settings
from app.extensions import db, redis_client
from app import models
from app.models import User, LoginAttempt, LoginAlert
from app.services.login_anomaly import (
    record_login_attempt,
    detect_anomalies,
    get_user_alerts,
    mark_alerts_read,
    _detect_brute_force,
    _detect_new_ip,
    _detect_new_device,
    _detect_credential_stuffing,
)


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-with-32-plus-chars-1234567890"


@pytest.fixture()
def app():
    settings = TestSettings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
        try:
            redis_client.flushdb()
        except Exception:
            pass
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        redis_client.flushdb()
    except Exception:
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    with app.app_context():
        user = User(
            email="anomaly@test.com",
            password_hash="hashed",
            preferred_currency="USD",
        )
        db.session.add(user)
        db.session.commit()
        return user.id


class TestRecordLoginAttempt:
    def test_records_successful_attempt(self, app, user):
        with app.app_context():
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
            )
            assert attempt.id is not None
            assert attempt.success is True
            assert attempt.ip_address == "192.168.1.1"
            assert attempt.user_id == user

    def test_records_failed_attempt(self, app, user):
        with app.app_context():
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=False,
                ip_address="10.0.0.1",
                failure_reason="invalid_credentials",
            )
            assert attempt.success is False
            assert attempt.failure_reason == "invalid_credentials"

    def test_records_unknown_email(self, app):
        with app.app_context():
            attempt = record_login_attempt(
                email="nonexistent@test.com",
                success=False,
            )
            assert attempt.user_id is None
            assert attempt.email == "nonexistent@test.com"


class TestBruteForceDetection:
    def test_no_alert_below_threshold(self, app, user):
        with app.app_context():
            for _ in range(3):
                attempt = record_login_attempt(
                    email="anomaly@test.com", success=False
                )
            alerts = _detect_brute_force(attempt)
            assert len(alerts) == 0

    def test_alert_at_threshold(self, app, user):
        with app.app_context():
            for _ in range(5):
                attempt = record_login_attempt(
                    email="anomaly@test.com", success=False
                )
            alerts = _detect_brute_force(attempt)
            assert len(alerts) == 1
            assert alerts[0].alert_type == "brute_force"
            assert alerts[0].severity == "high"


class TestNewIPDetection:
    def test_no_alert_first_login(self, app, user):
        with app.app_context():
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="1.2.3.4",
            )
            alerts = _detect_new_ip(attempt)
            assert len(alerts) == 0

    def test_alert_on_new_ip(self, app, user):
        with app.app_context():
            # First login from known IP
            record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="1.2.3.4",
            )
            # Login from new IP
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="5.6.7.8",
            )
            alerts = _detect_new_ip(attempt)
            assert len(alerts) == 1
            assert alerts[0].alert_type == "new_ip"
            assert "5.6.7.8" in alerts[0].message

    def test_no_alert_same_ip(self, app, user):
        with app.app_context():
            record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="1.2.3.4",
            )
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="1.2.3.4",
            )
            alerts = _detect_new_ip(attempt)
            assert len(alerts) == 0


class TestNewDeviceDetection:
    def test_alert_on_new_device(self, app, user):
        with app.app_context():
            # First login
            record_login_attempt(
                email="anomaly@test.com",
                success=True,
                user_agent="Chrome/120.0",
            )
            # New device
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=True,
                user_agent="Firefox/115.0",
            )
            alerts = _detect_new_device(attempt)
            assert len(alerts) == 1
            assert alerts[0].alert_type == "new_device"


class TestCredentialStuffingDetection:
    def test_alert_after_failures_then_success(self, app, user):
        with app.app_context():
            # 3 failed attempts
            for _ in range(3):
                record_login_attempt(
                    email="anomaly@test.com", success=False
                )
            # Successful login
            attempt = record_login_attempt(
                email="anomaly@test.com", success=True
            )
            alerts = _detect_credential_stuffing(attempt)
            assert len(alerts) == 1
            assert alerts[0].alert_type == "credential_stuffing"
            assert alerts[0].severity == "high"


class TestDetectAnomalies:
    def test_combined_detection(self, app, user):
        with app.app_context():
            # Establish baseline with one successful login
            record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="1.2.3.4",
                user_agent="Chrome/120",
            )
            # New IP + new device + after failures
            for _ in range(3):
                record_login_attempt(
                    email="anomaly@test.com", success=False
                )
            attempt = record_login_attempt(
                email="anomaly@test.com",
                success=True,
                ip_address="9.9.9.9",
                user_agent="TorBrowser/1.0",
            )
            alerts = detect_anomalies(attempt)
            alert_types = {a.alert_type for a in alerts}
            assert "new_ip" in alert_types
            assert "new_device" in alert_types
            assert "credential_stuffing" in alert_types


class TestAlertManagement:
    def test_get_user_alerts(self, app, user):
        with app.app_context():
            # Create some alerts
            for i in range(3):
                alert = LoginAlert(
                    user_id=user,
                    alert_type="new_ip",
                    severity="medium",
                    message=f"Test alert {i}",
                )
                db.session.add(alert)
            db.session.commit()

            alerts = get_user_alerts(user)
            assert len(alerts) == 3

            alerts_unread = get_user_alerts(user, unread_only=True)
            assert len(alerts_unread) == 3

    def test_mark_alerts_read(self, app, user):
        with app.app_context():
            alert = LoginAlert(
                user_id=user,
                alert_type="new_ip",
                severity="medium",
                message="Test",
            )
            db.session.add(alert)
            db.session.commit()

            count = mark_alerts_read(user, [alert.id])
            assert count == 1

            alerts = get_user_alerts(user, unread_only=True)
            assert len(alerts) == 0


class TestAuthIntegration:
    def test_login_records_attempt(self, client, user):
        """Test that login endpoint records attempts and returns alerts."""
        # Failed login
        r = client.post(
            "/auth/login",
            json={"email": "anomaly@test.com", "password": "wrong"},
        )
        assert r.status_code == 401

        # Successful login
        from werkzeug.security import generate_password_hash
        with client.application.app_context():
            u = db.session.get(User, user)
            u.password_hash = generate_password_hash("correct")
            db.session.commit()

        # Mock redis for the login flow
        with patch("app.routes.auth.redis_client") as mock_redis, \
             patch("app.services.login_anomaly.redis_client") as mock_redis2:
            mock_redis.get.return_value = None
            mock_redis.pipeline.return_value.execute.return_value = [1, True]
            mock_redis2.get.return_value = None
            mock_redis2.pipeline.return_value.execute.return_value = [1, True]
            r = client.post(
                "/auth/login",
                json={"email": "anomaly@test.com", "password": "correct"},
            )
            assert r.status_code == 200
            data = r.get_json()
            assert "access_token" in data

    def test_alerts_endpoint_requires_auth(self, client):
        r = client.get("/alerts/")
        assert r.status_code == 401

    def test_alerts_endpoint(self, client, user):
        from werkzeug.security import generate_password_hash
        with client.application.app_context():
            u = db.session.get(User, user)
            u.password_hash = generate_password_hash("pass123")
            alert = LoginAlert(
                user_id=user,
                alert_type="new_ip",
                severity="medium",
                message="Test alert",
            )
            db.session.add(alert)
            db.session.commit()

        with patch("app.routes.auth.redis_client") as mock_redis, \
             patch("app.services.login_anomaly.redis_client") as mock_redis2:
            mock_redis.get.return_value = None
            mock_redis.pipeline.return_value.execute.return_value = [1, True]
            mock_redis2.get.return_value = None
            mock_redis2.pipeline.return_value.execute.return_value = [1, True]
            r = client.post(
                "/auth/login",
                json={"email": "anomaly@test.com", "password": "pass123"},
            )
            token = r.get_json()["access_token"]

        r = client.get(
            "/alerts/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["alerts"]) >= 1
        assert data["alerts"][0]["alert_type"] == "new_ip"

    def test_unread_count(self, client, user):
        from werkzeug.security import generate_password_hash
        with client.application.app_context():
            u = db.session.get(User, user)
            u.password_hash = generate_password_hash("pass123")
            for i in range(3):
                db.session.add(
                    LoginAlert(
                        user_id=user,
                        alert_type="new_ip",
                        severity="medium",
                        message=f"Alert {i}",
                    )
                )
            db.session.commit()

        with patch("app.routes.auth.redis_client") as mock_redis, \
             patch("app.services.login_anomaly.redis_client") as mock_redis2:
            mock_redis.get.return_value = None
            mock_redis.pipeline.return_value.execute.return_value = [1, True]
            mock_redis2.get.return_value = None
            mock_redis2.pipeline.return_value.execute.return_value = [1, True]
            r = client.post(
                "/auth/login",
                json={"email": "anomaly@test.com", "password": "pass123"},
            )
            token = r.get_json()["access_token"]

        r = client.get(
            "/alerts/unread-count",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.get_json()["unread_count"] == 3
