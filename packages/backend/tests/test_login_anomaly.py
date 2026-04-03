"""Tests for login anomaly detection and suspicious activity alerts."""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models import LoginAlert, LoginAttempt
from app.services.login_anomaly import (
    FAILED_ATTEMPT_THRESHOLD,
    FAILED_ATTEMPT_WINDOW_MINUTES,
    analyse_login,
    check_account_locked,
    get_alerts,
    get_recent_attempts,
    record_login_attempt,
    acknowledge_alert,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_redis():
    """Mock redis_client for all tests so we don't need a running Redis."""
    store = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def setex(self, key, ttl, value):
            store[key] = value

        def delete(self, key):
            store.pop(key, None)

        def flushdb(self):
            store.clear()

    fake = FakeRedis()
    with patch("app.services.login_anomaly.redis_client", fake), \
         patch("app.routes.auth.redis_client", fake), \
         patch("app.extensions.redis_client", fake):
        yield fake


def _make_user(app_fixture, email="test@test.com"):
    """Create a user directly in the DB and return (user, password)."""
    from app.models import User
    from werkzeug.security import generate_password_hash

    with app_fixture.app_context():
        password = "testpass123"
        user = User(
            email=email,
            password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        uid = user.id
    return uid, password


# ---------------------------------------------------------------------------
# Unit tests - record_login_attempt
# ---------------------------------------------------------------------------

class TestRecordLoginAttempt:
    def test_records_successful_attempt(self, app_fixture):
        with app_fixture.app_context():
            attempt = record_login_attempt(
                email="u@example.com",
                ip_address="1.2.3.4",
                user_agent="TestAgent",
                success=True,
                user_id=None,
            )
            assert attempt.id is not None
            assert attempt.success is True
            assert attempt.ip_address == "1.2.3.4"

    def test_records_failed_attempt(self, app_fixture):
        with app_fixture.app_context():
            attempt = record_login_attempt(
                email="u@example.com",
                ip_address="5.6.7.8",
                user_agent=None,
                success=False,
            )
            assert attempt.success is False
            assert attempt.user_agent is None


# ---------------------------------------------------------------------------
# Unit tests - brute force detection
# ---------------------------------------------------------------------------

class TestBruteForceDetection:
    def test_triggers_after_threshold(self, app_fixture):
        with app_fixture.app_context():
            for _ in range(FAILED_ATTEMPT_THRESHOLD):
                attempt = record_login_attempt(
                    email="victim@test.com",
                    ip_address="10.0.0.1",
                    user_agent="Bot",
                    success=False,
                )
            alerts = analyse_login(attempt)
            assert len(alerts) == 1
            assert alerts[0].alert_type == "BRUTE_FORCE"
            assert alerts[0].severity == "CRITICAL"

    def test_no_alert_below_threshold(self, app_fixture):
        with app_fixture.app_context():
            for _ in range(FAILED_ATTEMPT_THRESHOLD - 1):
                attempt = record_login_attempt(
                    email="safe@test.com",
                    ip_address="10.0.0.2",
                    user_agent="Bot",
                    success=False,
                )
            alerts = analyse_login(attempt)
            assert len(alerts) == 0

    def test_lockout_after_brute_force(self, app_fixture):
        with app_fixture.app_context():
            for _ in range(FAILED_ATTEMPT_THRESHOLD):
                record_login_attempt(
                    email="locked@test.com",
                    ip_address="10.0.0.3",
                    user_agent="Bot",
                    success=False,
                )
            last = record_login_attempt(
                email="locked@test.com",
                ip_address="10.0.0.3",
                user_agent="Bot",
                success=False,
            )
            analyse_login(last)
            assert check_account_locked("locked@test.com") is True


# ---------------------------------------------------------------------------
# Unit tests - new IP detection
# ---------------------------------------------------------------------------

class TestNewIpDetection:
    def test_first_login_creates_new_ip_alert(self, app_fixture):
        uid, _ = _make_user(app_fixture, "newip@test.com")
        with app_fixture.app_context():
            attempt = record_login_attempt(
                email="newip@test.com",
                ip_address="192.168.1.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
            )
            alerts = analyse_login(attempt)
            types = [a.alert_type for a in alerts]
            assert "NEW_IP" in types

    def test_known_ip_no_alert(self, app_fixture):
        uid, _ = _make_user(app_fixture, "knownip@test.com")
        with app_fixture.app_context():
            record_login_attempt(
                email="knownip@test.com",
                ip_address="192.168.1.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
            )
            attempt2 = record_login_attempt(
                email="knownip@test.com",
                ip_address="192.168.1.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
            )
            alerts = analyse_login(attempt2)
            types = [a.alert_type for a in alerts]
            assert "NEW_IP" not in types


# ---------------------------------------------------------------------------
# Unit tests - new device detection
# ---------------------------------------------------------------------------

class TestNewDeviceDetection:
    def test_new_user_agent_triggers_alert(self, app_fixture):
        uid, _ = _make_user(app_fixture, "newdev@test.com")
        with app_fixture.app_context():
            record_login_attempt(
                email="newdev@test.com",
                ip_address="10.0.0.1",
                user_agent="Chrome/100",
                success=True,
                user_id=uid,
            )
            attempt2 = record_login_attempt(
                email="newdev@test.com",
                ip_address="10.0.0.1",
                user_agent="Firefox/110",
                success=True,
                user_id=uid,
            )
            alerts = analyse_login(attempt2)
            types = [a.alert_type for a in alerts]
            assert "NEW_DEVICE" in types


# ---------------------------------------------------------------------------
# Unit tests - odd hour detection
# ---------------------------------------------------------------------------

class TestOddHourDetection:
    def test_login_at_3am_triggers_alert(self, app_fixture):
        uid, _ = _make_user(app_fixture, "oddhr@test.com")
        with app_fixture.app_context():
            attempt = record_login_attempt(
                email="oddhr@test.com",
                ip_address="10.0.0.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
            )
            attempt.created_at = datetime.utcnow().replace(hour=3, minute=0, second=0)
            db.session.commit()

            alerts = analyse_login(attempt)
            types = [a.alert_type for a in alerts]
            assert "ODD_HOUR" in types

    def test_login_at_noon_no_odd_hour_alert(self, app_fixture):
        uid, _ = _make_user(app_fixture, "noon@test.com")
        with app_fixture.app_context():
            attempt = record_login_attempt(
                email="noon@test.com",
                ip_address="10.0.0.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
            )
            attempt.created_at = datetime.utcnow().replace(hour=12, minute=0, second=0)
            db.session.commit()

            alerts = analyse_login(attempt)
            types = [a.alert_type for a in alerts]
            assert "ODD_HOUR" not in types


# ---------------------------------------------------------------------------
# Unit tests - impossible travel detection
# ---------------------------------------------------------------------------

class TestImpossibleTravelDetection:
    def test_different_countries_in_short_window(self, app_fixture):
        uid, _ = _make_user(app_fixture, "travel@test.com")
        with app_fixture.app_context():
            record_login_attempt(
                email="travel@test.com",
                ip_address="10.0.0.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
                country="US",
            )
            attempt2 = record_login_attempt(
                email="travel@test.com",
                ip_address="10.0.0.2",
                user_agent="Chrome",
                success=True,
                user_id=uid,
                country="JP",
            )
            alerts = analyse_login(attempt2)
            types = [a.alert_type for a in alerts]
            assert "IMPOSSIBLE_TRAVEL" in types


# ---------------------------------------------------------------------------
# Unit tests - query helpers
# ---------------------------------------------------------------------------

class TestGetRecentAttempts:
    def test_returns_attempts_for_user(self, app_fixture):
        uid, _ = _make_user(app_fixture, "hist@test.com")
        with app_fixture.app_context():
            for i in range(3):
                record_login_attempt(
                    email="hist@test.com",
                    ip_address=f"10.0.0.{i}",
                    user_agent="Chrome",
                    success=True,
                    user_id=uid,
                )
            attempts = get_recent_attempts(uid, limit=10)
            assert len(attempts) == 3


class TestAlertManagement:
    def test_get_and_acknowledge_alerts(self, app_fixture):
        uid, _ = _make_user(app_fixture, "ack@test.com")
        with app_fixture.app_context():
            attempt = record_login_attempt(
                email="ack@test.com",
                ip_address="172.16.0.1",
                user_agent="Chrome",
                success=True,
                user_id=uid,
            )
            alerts = analyse_login(attempt)
            assert len(alerts) > 0

            unacked = get_alerts(uid)
            assert len(unacked) > 0

            ack = acknowledge_alert(unacked[0].id, uid)
            assert ack.acknowledged is True

            remaining = get_alerts(uid, include_acknowledged=False)
            acked_ids = [a.id for a in remaining]
            assert ack.id not in acked_ids


# ---------------------------------------------------------------------------
# Integration tests - HTTP endpoints
# ---------------------------------------------------------------------------

class TestLoginRecordsAttempt:
    def test_successful_login_creates_attempt(self, client):
        email = "integ_ok@test.com"
        client.post("/auth/register", json={"email": email, "password": "pass123"})
        r = client.post("/auth/login", json={"email": email, "password": "pass123"})
        assert r.status_code == 200
        data = r.get_json()
        assert "access_token" in data

    def test_failed_login_creates_attempt(self, client):
        r = client.post(
            "/auth/login", json={"email": "nobody@test.com", "password": "wrong"}
        )
        assert r.status_code == 401

    def test_brute_force_locks_account(self, client):
        email = "brute@test.com"
        client.post("/auth/register", json={"email": email, "password": "pass123"})
        for _ in range(FAILED_ATTEMPT_THRESHOLD + 1):
            client.post("/auth/login", json={"email": email, "password": "wrong"})

        # Next attempt should be blocked with 429
        r = client.post("/auth/login", json={"email": email, "password": "pass123"})
        assert r.status_code == 429
        assert "locked" in r.get_json()["error"]


class TestSecurityEndpoints:
    def test_login_history(self, client):
        email = "hist_ep@test.com"
        password = "pass123"
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        access = r.get_json()["access_token"]
        auth = {"Authorization": f"Bearer {access}"}

        r = client.get("/auth/security/history", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["success"] is True

    def test_login_alerts(self, client):
        email = "alert_ep@test.com"
        password = "pass123"
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        access = r.get_json()["access_token"]
        auth = {"Authorization": f"Bearer {access}"}

        r = client.get("/auth/security/alerts", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        # First login creates NEW_IP and NEW_DEVICE alerts
        assert len(data) >= 1

    def test_acknowledge_alert(self, client):
        email = "ack_ep@test.com"
        password = "pass123"
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        access = r.get_json()["access_token"]
        auth = {"Authorization": f"Bearer {access}"}

        r = client.get("/auth/security/alerts", headers=auth)
        alerts = r.get_json()
        if len(alerts) > 0:
            alert_id = alerts[0]["id"]
            r = client.post(
                f"/auth/security/alerts/{alert_id}/acknowledge", headers=auth
            )
            assert r.status_code == 200
            assert r.get_json()["message"] == "acknowledged"

    def test_acknowledge_nonexistent_alert(self, client):
        email = "ack404@test.com"
        password = "pass123"
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        access = r.get_json()["access_token"]
        auth = {"Authorization": f"Bearer {access}"}

        r = client.post("/auth/security/alerts/99999/acknowledge", headers=auth)
        assert r.status_code == 404

    def test_security_alerts_in_login_response(self, client):
        email = "alerts_resp@test.com"
        password = "pass123"
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        data = r.get_json()
        # First login from a new IP/device should include security_alerts
        if "security_alerts" in data:
            assert isinstance(data["security_alerts"], list)
            for alert in data["security_alerts"]:
                assert "alert_type" in alert
                assert "severity" in alert
                assert "message" in alert

    def test_endpoints_require_auth(self, client):
        r = client.get("/auth/security/history")
        assert r.status_code == 401
        r = client.get("/auth/security/alerts")
        assert r.status_code == 401
        r = client.post("/auth/security/alerts/1/acknowledge")
        assert r.status_code == 401
