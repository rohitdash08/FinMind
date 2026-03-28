"""Tests for login anomaly detection — service + security API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from app.extensions import db
from app.models import LoginEvent, User
from werkzeug.security import generate_password_hash

from app.services.login_anomaly import (
    compute_anomaly_score,
    record_login,
    BRUTE_FORCE_WINDOW_MINUTES,
    BRUTE_FORCE_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Fixture: patch redis so API route tests don't need a live Redis
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def mock_redis(monkeypatch):
    """Replace the live redis_client with a simple in-memory MagicMock."""
    store: dict = {}

    mock = MagicMock()
    mock.get.side_effect = lambda key: store.get(key)
    mock.setex.side_effect = lambda key, _ttl, val: store.update({key: val})
    mock.delete.side_effect = lambda key: store.pop(key, None)
    mock.flushdb.side_effect = lambda: store.clear()

    import app.routes.auth as auth_module
    monkeypatch.setattr(auth_module, "redis_client", mock)
    import app.extensions as ext_module
    monkeypatch.setattr(ext_module, "redis_client", mock)
    return mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email: str = "test@example.com") -> User:
    user = User(
        email=email,
        password_hash=generate_password_hash("pass"),
        preferred_currency="INR",
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login_event(user_id: int, ip: str, ua: str, success: bool, score: float = 0.0):
    evt = LoginEvent(
        user_id=user_id,
        ip_address=ip,
        user_agent=ua,
        success=success,
        anomaly_score=score,
    )
    db.session.add(evt)
    db.session.commit()
    return evt


# ---------------------------------------------------------------------------
# Service: compute_anomaly_score
# ---------------------------------------------------------------------------


class TestComputeAnomalyScore:
    def test_first_login_returns_zero_score(self, app_fixture):
        """A brand-new user with no history has no anomalies."""
        with app_fixture.app_context():
            user = _make_user()
            score, reasons = compute_anomaly_score(
                user.id, "1.2.3.4", "TestBrowser/1.0", success=True
            )
            assert score == 0.0
            assert reasons == []

    def test_new_ip_detected(self, app_fixture):
        """Login from a new IP after an established one raises score."""
        with app_fixture.app_context():
            user = _make_user("newip@example.com")
            # Seed a successful login from the "known" IP
            _login_event(user.id, "10.0.0.1", "UA/1", success=True)

            score, reasons = compute_anomaly_score(
                user.id, "192.168.99.1", "UA/1", success=True
            )
            assert score > 0
            assert any("new IP" in r for r in reasons)

    def test_known_ip_not_flagged(self, app_fixture):
        """Login from a previously seen IP is NOT flagged for IP."""
        with app_fixture.app_context():
            user = _make_user("knownip@example.com")
            _login_event(user.id, "10.0.0.1", "UA/1", success=True)

            score, reasons = compute_anomaly_score(
                user.id, "10.0.0.1", "UA/1", success=True
            )
            assert not any("new IP" in r for r in reasons)

    def test_new_device_detected(self, app_fixture):
        """Login from a new user-agent raises score."""
        with app_fixture.app_context():
            user = _make_user("newdev@example.com")
            _login_event(user.id, "10.0.0.1", "KnownBrowser/1.0", success=True)

            score, reasons = compute_anomaly_score(
                user.id, "10.0.0.1", "UnknownBrowser/99.0", success=True
            )
            assert score > 0
            assert any("new device" in r for r in reasons)

    def test_brute_force_detected(self, app_fixture):
        """Too many failures in the window should be flagged."""
        with app_fixture.app_context():
            user = _make_user("brute@example.com")
            # Insert BRUTE_FORCE_THRESHOLD failed events within the window
            for _ in range(BRUTE_FORCE_THRESHOLD):
                _login_event(user.id, "10.0.0.1", "UA/1", success=False)

            score, reasons = compute_anomaly_score(
                user.id, "10.0.0.1", "UA/1", success=True
            )
            assert score > 0
            assert any("failed login" in r for r in reasons)

    def test_brute_force_not_triggered_below_threshold(self, app_fixture):
        """Fewer failures than the threshold should not trigger brute-force."""
        with app_fixture.app_context():
            user = _make_user("nobrute@example.com")
            for _ in range(BRUTE_FORCE_THRESHOLD - 1):
                _login_event(user.id, "10.0.0.1", "UA/1", success=False)

            score, reasons = compute_anomaly_score(
                user.id, "10.0.0.1", "UA/1", success=True
            )
            assert not any("failed login" in r for r in reasons)

    def test_unusual_hour_flagged(self, app_fixture):
        """A login at 3 AM UTC should be flagged."""
        with app_fixture.app_context():
            user = _make_user("oddhour@example.com")
            odd_hour_ts = datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc)
            score, reasons = compute_anomaly_score(
                user.id, "10.0.0.1", "UA/1", success=True, now=odd_hour_ts
            )
            assert any("unusual hour" in r for r in reasons)

    def test_normal_hour_not_flagged(self, app_fixture):
        """A login at 10 AM UTC should NOT be flagged for unusual hour."""
        with app_fixture.app_context():
            user = _make_user("normalhour@example.com")
            normal_ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            score, reasons = compute_anomaly_score(
                user.id, "10.0.0.1", "UA/1", success=True, now=normal_ts
            )
            assert not any("unusual hour" in r for r in reasons)

    def test_score_capped_at_one(self, app_fixture):
        """Composite score should never exceed 1.0."""
        with app_fixture.app_context():
            user = _make_user("cap@example.com")
            _login_event(user.id, "10.0.0.1", "UA/1", success=True)
            # Many failures for brute force
            for _ in range(BRUTE_FORCE_THRESHOLD + 5):
                _login_event(user.id, "10.0.0.1", "UA/1", success=False)

            odd_ts = datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc)
            score, _ = compute_anomaly_score(
                user.id, "9.9.9.9", "NewBrowser/2.0", success=True, now=odd_ts
            )
            assert score <= 1.0


# ---------------------------------------------------------------------------
# Service: record_login
# ---------------------------------------------------------------------------


class TestRecordLogin:
    def test_records_event_in_db(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("recorder@example.com")
            event = record_login(user.id, "10.0.0.1", "UA/1", success=True)
            assert event.id is not None
            assert event.user_id == user.id
            assert event.success is True

    def test_failed_login_recorded(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("fail@example.com")
            event = record_login(user.id, "10.0.0.1", "UA/1", success=False)
            assert event.success is False


# ---------------------------------------------------------------------------
# API: /security endpoints
# ---------------------------------------------------------------------------


class TestSecurityRoutes:
    def _register_and_login(self, client, email="sec@example.com", pw="pass1234"):
        client.post("/auth/register", json={"email": email, "password": pw})
        r = client.post("/auth/login", json={"email": email, "password": pw})
        token = r.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture(autouse=True)
    def _use_mock_redis(self, mock_redis):
        """Ensure all tests in this class use the mocked Redis."""
        pass

    def test_login_history_empty(self, client, app_fixture):
        headers = self._register_and_login(client)
        r = client.get("/security/login-history", headers=headers)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        # At least the login above is recorded
        assert len(data) >= 1

    def test_login_history_requires_auth(self, client):
        r = client.get("/security/login-history")
        assert r.status_code == 401

    def test_anomalies_endpoint(self, client, app_fixture):
        headers = self._register_and_login(client, "anom@example.com")
        r = client.get("/security/anomalies", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_login_stats_structure(self, client, app_fixture):
        headers = self._register_and_login(client, "stats@example.com")
        r = client.get("/security/login-stats", headers=headers)
        assert r.status_code == 200
        data = r.get_json()
        assert "total_logins" in data
        assert "unique_ips" in data
        assert "unique_devices" in data
        assert "suspicious_count" in data
        assert "last_anomaly" in data

    def test_login_stats_total_increments(self, client, app_fixture):
        """Each login increments total_logins."""
        email, pw = "incr@example.com", "pass1234"
        client.post("/auth/register", json={"email": email, "password": pw})

        def get_total(h):
            return client.get("/security/login-stats", headers=h).get_json()[
                "total_logins"
            ]

        r1 = client.post("/auth/login", json={"email": email, "password": pw})
        h1 = {"Authorization": f"Bearer {r1.get_json()['access_token']}"}
        before = get_total(h1)

        client.post("/auth/login", json={"email": email, "password": pw})
        after = get_total(h1)
        assert after == before + 1

    def test_anomalies_requires_auth(self, client):
        r = client.get("/security/anomalies")
        assert r.status_code == 401

    def test_login_stats_requires_auth(self, client):
        r = client.get("/security/login-stats")
        assert r.status_code == 401

    def test_failed_login_recorded_as_event(self, client, app_fixture):
        """Failed logins should appear in login history (success=False)."""
        email, pw = "failrec@example.com", "rightpass"
        client.post("/auth/register", json={"email": email, "password": pw})
        # Intentional failed attempt
        client.post("/auth/login", json={"email": email, "password": "wrongpass"})
        # Successful login
        r = client.post("/auth/login", json={"email": email, "password": pw})
        h = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

        history = client.get("/security/login-history", headers=h).get_json()
        # At least the successful login is present; failed is also recorded
        successes = [e for e in history if e["success"]]
        failures = [e for e in history if not e["success"]]
        assert len(successes) >= 1
        assert len(failures) >= 1
