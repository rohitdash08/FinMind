"""Tests for login anomaly detection & security alerts (Bounty #124)."""
from unittest.mock import patch
from datetime import datetime, timezone

import pytest
from app.extensions import db, redis_client
from app.models import AuditLog, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
EMAIL = "security_user@test.com"
PASSWORD = "securepass99!"
WRONG_PW = "wrongpass"


def _register(client, email=EMAIL, password=PASSWORD):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)


def _login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _auth_header(client, email=EMAIL, password=PASSWORD):
    _register(client, email, password)
    r = _login(client, email, password)
    assert r.status_code == 200, r.get_json()
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _flush_auth_keys():
    """Delete all auth:* keys from Redis between tests."""
    try:
        for key in redis_client.keys("auth:*"):
            redis_client.delete(key)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Brute-force protection
# ---------------------------------------------------------------------------

class TestBruteForceProtection:

    def setup_method(self):
        _flush_auth_keys()

    def test_failed_login_returns_401(self, client, app_fixture):
        _register(client)
        r = _login(client, password=WRONG_PW)
        assert r.status_code == 401
        assert "invalid" in r.get_json().get("error", "").lower()

    def test_missing_fields_returns_400(self, client):
        r = client.post("/auth/login", json={})
        assert r.status_code == 400

    def test_brute_force_blocked_after_five_failures(self, client, app_fixture):
        _register(client)
        # Make 5 failed attempts
        for _ in range(5):
            r = _login(client, password=WRONG_PW)
            if r.status_code == 429:
                break
        # 6th attempt should always be 429
        r = _login(client, password=WRONG_PW)
        assert r.status_code == 429
        assert r.get_json().get("error") == "too_many_attempts"

    def test_brute_force_blocked_even_with_correct_password(self, client, app_fixture):
        """After threshold, correct password is also blocked."""
        _register(client)
        for _ in range(5):
            _login(client, password=WRONG_PW)
        r = _login(client)  # correct password
        assert r.status_code == 429

    def test_successful_login_resets_failure_counter(self, client, app_fixture):
        _register(client)
        # Make 3 failed attempts (below threshold)
        for _ in range(3):
            _login(client, password=WRONG_PW)
        # Successful login resets counter
        r = _login(client)
        assert r.status_code == 200
        # Next failure should start fresh (not immediately blocked)
        r = _login(client, password=WRONG_PW)
        assert r.status_code == 401  # not 429

    def test_login_success_returns_tokens(self, client, app_fixture):
        _register(client)
        r = _login(client)
        assert r.status_code == 200
        data = r.get_json()
        assert "access_token" in data
        assert "refresh_token" in data


# ---------------------------------------------------------------------------
# Redis event logging
# ---------------------------------------------------------------------------

class TestRedisEventLogging:

    def setup_method(self):
        _flush_auth_keys()

    def test_login_event_stored_in_redis(self, client, app_fixture):
        _register(client)
        r = _login(client)
        assert r.status_code == 200
        # Get user id
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=EMAIL).first()
            uid = user.id
        keys = redis_client.keys(f"auth:login_event:{uid}:*")
        assert len(keys) >= 1

    def test_login_event_has_correct_ttl(self, client, app_fixture):
        _register(client)
        _login(client)
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=EMAIL).first()
            uid = user.id
        keys = redis_client.keys(f"auth:login_event:{uid}:*")
        for key in keys:
            ttl = redis_client.ttl(key)
            assert 0 < ttl <= 60 * 60 * 24 * 30  # max 30 days

    def test_failure_counter_incremented_in_redis(self, client, app_fixture):
        _register(client)
        _login(client, password=WRONG_PW)
        _login(client, password=WRONG_PW)
        key = f"auth:fails:127.0.0.1:{EMAIL}"
        val = redis_client.get(key)
        assert val is not None
        assert int(val) >= 2


# ---------------------------------------------------------------------------
# Unusual-hour detection
# ---------------------------------------------------------------------------

class TestUnusualHourDetection:

    def setup_method(self):
        _flush_auth_keys()

    def test_no_alert_during_normal_hour(self, client, app_fixture):
        _register(client)
        # Mock a safe hour (10:00 UTC)
        safe_time = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.security.datetime") as mock_dt:
            mock_dt.now.return_value = safe_time
            mock_dt.side_effect = None
            r = _login(client)
        assert r.status_code == 200
        assert "security_alert" not in r.get_json()

    def test_security_alert_during_suspicious_hour(self, client, app_fixture):
        _register(client)
        # Mock 02:34 UTC (within 01:00-05:00 window)
        suspicious_time = datetime(2026, 2, 20, 2, 34, 0, tzinfo=timezone.utc)
        with patch("app.services.security.datetime") as mock_dt:
            mock_dt.now.return_value = suspicious_time
            mock_dt.side_effect = None
            r = _login(client)
        assert r.status_code == 200
        data = r.get_json()
        assert "security_alert" in data
        assert "02:34" in data["security_alert"]
        assert "unusual" in data["security_alert"].lower()

    def test_no_alert_at_hour_boundary_5(self, client, app_fixture):
        """05:00 UTC is outside the suspicious window."""
        _register(client)
        safe_time = datetime(2026, 2, 20, 5, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.security.datetime") as mock_dt:
            mock_dt.now.return_value = safe_time
            mock_dt.side_effect = None
            r = _login(client)
        assert r.status_code == 200
        assert "security_alert" not in r.get_json()


# ---------------------------------------------------------------------------
# Security-events endpoint
# ---------------------------------------------------------------------------

class TestSecurityEventsEndpoint:

    def setup_method(self):
        _flush_auth_keys()

    def test_requires_authentication(self, client):
        r = client.get("/auth/security-events")
        assert r.status_code == 401

    def test_returns_events_list(self, client, app_fixture):
        auth = _auth_header(client)
        r = client.get("/auth/security-events", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_events_contain_login_after_login(self, client, app_fixture):
        auth = _auth_header(client)
        r = client.get("/auth/security-events", headers=auth)
        assert r.status_code == 200
        events = r.get_json()["events"]
        assert len(events) >= 1
        event = events[0]
        assert "ip" in event
        assert "timestamp" in event
        assert "hour" in event

    def test_events_capped_at_ten(self, client, app_fixture):
        """Even with many logins, at most 10 events returned."""
        _register(client)
        # Log 12 login events directly
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=EMAIL).first()
            uid = user.id
        from app.services.security import store_login_event
        with app_fixture.app_context():
            for _ in range(12):
                store_login_event(uid, "127.0.0.1")
        # Login to get token
        r = _login(client)
        token = r.get_json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        r = client.get("/auth/security-events", headers=auth)
        assert r.status_code == 200
        assert len(r.get_json()["events"]) <= 10

    def test_events_sorted_newest_first(self, client, app_fixture):
        """Events must be in descending timestamp order."""
        auth = _auth_header(client)
        r = client.get("/auth/security-events", headers=auth)
        events = r.get_json()["events"]
        if len(events) >= 2:
            timestamps = [e["timestamp"] for e in events]
            assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# AuditLog persistence
# ---------------------------------------------------------------------------

class TestAuditLog:

    def setup_method(self):
        _flush_auth_keys()

    def test_failed_login_creates_audit_log(self, client, app_fixture):
        _register(client)
        _login(client, password=WRONG_PW)
        with app_fixture.app_context():
            log = (
                db.session.query(AuditLog)
                .filter_by(action="login_failed")
                .first()
            )
            assert log is not None

    def test_successful_login_creates_audit_log(self, client, app_fixture):
        _register(client)
        _login(client)
        with app_fixture.app_context():
            log = (
                db.session.query(AuditLog)
                .filter_by(action="login_success")
                .first()
            )
            assert log is not None

    def test_brute_force_blocked_creates_audit_log(self, client, app_fixture):
        _register(client)
        for _ in range(6):
            _login(client, password=WRONG_PW)
        with app_fixture.app_context():
            log = (
                db.session.query(AuditLog)
                .filter_by(action="brute_force_blocked")
                .first()
            )
            assert log is not None


# ---------------------------------------------------------------------------
# Security service unit tests
# ---------------------------------------------------------------------------

class TestSecurityServiceUnit:

    def setup_method(self):
        _flush_auth_keys()

    def test_failure_count_increments(self, app_fixture):
        from app.services.security import record_failed_login, get_failure_count
        with app_fixture.app_context():
            ip, email = "1.2.3.4", "unit@test.com"
            c1 = record_failed_login(ip, email)
            c2 = record_failed_login(ip, email)
            assert c2 == c1 + 1
            assert get_failure_count(ip, email) == c2

    def test_brute_force_threshold(self, app_fixture):
        from app.services.security import record_failed_login, is_brute_force
        with app_fixture.app_context():
            ip, email = "5.6.7.8", "brute@test.com"
            for _ in range(5):
                record_failed_login(ip, email)
            assert is_brute_force(ip, email) is True

    def test_reset_clears_counter(self, app_fixture):
        from app.services.security import record_failed_login, reset_failure_count, get_failure_count
        with app_fixture.app_context():
            ip, email = "9.8.7.6", "reset@test.com"
            record_failed_login(ip, email)
            record_failed_login(ip, email)
            reset_failure_count(ip, email)
            assert get_failure_count(ip, email) == 0

    def test_detect_unusual_hour_window(self, app_fixture):
        from app.services.security import detect_unusual_hour
        with app_fixture.app_context():
            for hour in [1, 2, 3, 4]:
                t = datetime(2026, 2, 20, hour, 0, 0, tzinfo=timezone.utc)
                with patch("app.services.security.datetime") as mock_dt:
                    mock_dt.now.return_value = t
                    result = detect_unusual_hour()
                assert result is not None, f"Expected alert at hour {hour}"

    def test_detect_no_alert_outside_window(self, app_fixture):
        from app.services.security import detect_unusual_hour
        with app_fixture.app_context():
            for hour in [0, 5, 6, 12, 23]:
                t = datetime(2026, 2, 20, hour, 0, 0, tzinfo=timezone.utc)
                with patch("app.services.security.datetime") as mock_dt:
                    mock_dt.now.return_value = t
                    result = detect_unusual_hour()
                assert result is None, f"Expected no alert at hour {hour}"
