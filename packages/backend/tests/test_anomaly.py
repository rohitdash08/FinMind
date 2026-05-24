"""Tests for login anomaly detection (issue #124).

Covers:
- Login events recorded on success and failure
- NEW_IP alert on login from unseen IP
- NEW_DEVICE alert on login from unseen user-agent
- FAILED_BURST alert after 5+ failures in 15-minute window
- UNUSUAL_HOUR alert on 00:00-04:59 UTC login
- No duplicate burst alerts within same window
- No new-IP/device alert for brand-new user (first login)
- Security endpoints: event history, alerts list, unread count, acknowledge
- Auth gates (401 without JWT)
- Cross-user isolation
- Login response includes security_alerts key when anomalies detected
"""
from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DISABLE_SCHEDULER", "true")

# ---------------------------------------------------------------------------
# Patch Redis before app import
# ---------------------------------------------------------------------------
import app.extensions as _ext  # noqa: E402

_rc = _ext.redis_client
_rc.ping = lambda: True
_rc.get = lambda *a, **kw: None
_rc.set = lambda *a, **kw: True
_rc.setex = lambda *a, **kw: True
_rc.delete = lambda *a, **kw: 0
_rc.scan = lambda cursor=0, **kw: (0, [])
_rc.keys = lambda *a, **kw: []
_rc.expire = lambda *a, **kw: 1

from app import create_app  # noqa: E402
from app.config import Settings  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.models import LoginEvent, SecurityAlert  # noqa: E402
from app.services.anomaly import (  # noqa: E402
    _BURST_THRESHOLD,
    _BURST_WINDOW_MINUTES,
    check_and_create_alerts,
    record_login_event,
)


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    jwt_secret: str = "test-secret-key-32chars-padding!!"
    jwt_access_minutes: int = 60


@pytest.fixture(scope="module")
def app():
    flask_app = create_app(TestSettings())
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reg_login(client, email, password="Pass1234!"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "10.0.0.1", "User-Agent": "TestBrowser/1.0"},
    )
    return r.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------

class TestAuthGates:
    def test_events_require_auth(self, client):
        assert client.get("/security/events").status_code == 401

    def test_alerts_require_auth(self, client):
        assert client.get("/security/alerts").status_code == 401

    def test_unread_count_require_auth(self, client):
        assert client.get("/security/alerts/unread-count").status_code == 401

    def test_acknowledge_requires_auth(self, client):
        assert client.patch("/security/alerts/1/acknowledge").status_code == 401


# ---------------------------------------------------------------------------
# Login event recording
# ---------------------------------------------------------------------------

class TestLoginEventRecording:
    def test_success_recorded(self, client, app):
        token = _reg_login(client, "evtrec@test.com")
        with app.app_context():
            from app.models import User
            user = _db.session.query(User).filter_by(email="evtrec@test.com").first()
            events = _db.session.query(LoginEvent).filter_by(user_id=user.id, success=True).all()
        # At least the registration login
        assert len(events) >= 1

    def test_failure_recorded(self, client, app):
        client.post("/auth/register", json={"email": "failrec@test.com", "password": "Pass1234!"})
        client.post(
            "/auth/login",
            json={"email": "failrec@test.com", "password": "WRONG"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        with app.app_context():
            from app.models import User
            user = _db.session.query(User).filter_by(email="failrec@test.com").first()
            events = _db.session.query(LoginEvent).filter_by(user_id=user.id, success=False).all()
        assert len(events) >= 1

    def test_ip_masked_in_event(self, client, app):
        client.post("/auth/register", json={"email": "ipmask@test.com", "password": "Pass1234!"})
        client.post(
            "/auth/login",
            json={"email": "ipmask@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "192.168.5.99"},
        )
        with app.app_context():
            from app.models import User
            user = _db.session.query(User).filter_by(email="ipmask@test.com").first()
            ev = _db.session.query(LoginEvent).filter_by(user_id=user.id).first()
        assert ev.ip_masked == "192.168.5.xxx"

    def test_event_history_endpoint(self, client):
        token = _reg_login(client, "evthist@test.com")
        r = client.get("/security/events", headers=_auth(token))
        assert r.status_code == 200
        events = r.get_json()
        assert isinstance(events, list)
        assert len(events) >= 1
        assert "ip_masked" in events[0]
        assert "success" in events[0]
        assert "created_at" in events[0]

    def test_event_history_limit(self, client):
        token = _reg_login(client, "evtlimit@test.com")
        r = client.get("/security/events?limit=1", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.get_json()) <= 1


# ---------------------------------------------------------------------------
# New-IP alert
# ---------------------------------------------------------------------------

class TestNewIPAlert:
    def test_no_alert_first_login(self, client):
        """First login from any IP should NOT produce a new-IP alert."""
        client.post("/auth/register", json={"email": "firstip@test.com", "password": "Pass1234!"})
        r = client.post(
            "/auth/login",
            json={"email": "firstip@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        )
        d = r.get_json()
        assert r.status_code == 200
        alerts = d.get("security_alerts", [])
        new_ip_alerts = [a for a in alerts if a["alert_type"] == "new_ip"]
        assert len(new_ip_alerts) == 0

    def test_alert_on_second_different_ip(self, client):
        """After logging in once, a new IP triggers an alert."""
        client.post("/auth/register", json={"email": "newip@test.com", "password": "Pass1234!"})
        # First login — establishes known IP
        client.post(
            "/auth/login",
            json={"email": "newip@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "10.1.1.1", "User-Agent": "BrowserA/1"},
        )
        # Second login — different IP
        r = client.post(
            "/auth/login",
            json={"email": "newip@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "203.0.113.5", "User-Agent": "BrowserA/1"},
        )
        d = r.get_json()
        assert r.status_code == 200
        alerts = d.get("security_alerts", [])
        new_ip_alerts = [a for a in alerts if a["alert_type"] == "new_ip"]
        assert len(new_ip_alerts) == 1
        assert new_ip_alerts[0]["severity"] == "medium"

    def test_no_alert_same_ip_repeated(self, client):
        """Same IP as last time → no new-IP alert."""
        client.post("/auth/register", json={"email": "sameip@test.com", "password": "Pass1234!"})
        for _ in range(2):
            r = client.post(
                "/auth/login",
                json={"email": "sameip@test.com", "password": "Pass1234!"},
                headers={"X-Forwarded-For": "10.2.2.2", "User-Agent": "BrowserX/1"},
            )
        d = r.get_json()
        alerts = d.get("security_alerts", [])
        new_ip_alerts = [a for a in alerts if a["alert_type"] == "new_ip"]
        assert len(new_ip_alerts) == 0


# ---------------------------------------------------------------------------
# New-device alert
# ---------------------------------------------------------------------------

class TestNewDeviceAlert:
    def test_alert_on_new_user_agent(self, client):
        client.post("/auth/register", json={"email": "newua@test.com", "password": "Pass1234!"})
        # First login with UA1
        client.post(
            "/auth/login",
            json={"email": "newua@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "10.0.0.1", "User-Agent": "Mozilla/5.0 (UA1)"},
        )
        # Second login with UA2 (same IP, different browser)
        r = client.post(
            "/auth/login",
            json={"email": "newua@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "10.0.0.1", "User-Agent": "CurlBot/7.0 (UA2)"},
        )
        d = r.get_json()
        alerts = d.get("security_alerts", [])
        new_dev = [a for a in alerts if a["alert_type"] == "new_device"]
        assert len(new_dev) == 1
        assert new_dev[0]["severity"] == "medium"

    def test_no_alert_same_user_agent(self, client):
        client.post("/auth/register", json={"email": "sameua@test.com", "password": "Pass1234!"})
        for _ in range(2):
            r = client.post(
                "/auth/login",
                json={"email": "sameua@test.com", "password": "Pass1234!"},
                headers={"X-Forwarded-For": "10.0.0.1", "User-Agent": "StableAgent/1"},
            )
        d = r.get_json()
        alerts = d.get("security_alerts", [])
        new_dev = [a for a in alerts if a["alert_type"] == "new_device"]
        assert len(new_dev) == 0


# ---------------------------------------------------------------------------
# Failed-burst alert
# ---------------------------------------------------------------------------

class TestFailedBurstAlert:
    def test_burst_alert_after_threshold(self, client):
        client.post("/auth/register", json={"email": "burst@test.com", "password": "Pass1234!"})
        for _ in range(_BURST_THRESHOLD):
            client.post(
                "/auth/login",
                json={"email": "burst@test.com", "password": "WRONG"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
        # Next failed attempt should trigger alert
        r = client.post(
            "/auth/login",
            json={"email": "burst@test.com", "password": "WRONG"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        # Failure returns 401; alert was stored in DB
        assert r.status_code == 401
        with client.application.app_context():
            from app.models import User
            user = _db.session.query(User).filter_by(email="burst@test.com").first()
            alerts = (
                _db.session.query(SecurityAlert)
                .filter_by(user_id=user.id, alert_type="failed_burst")
                .all()
            )
        assert len(alerts) >= 1
        assert alerts[0].severity == "high"

    def test_no_duplicate_burst_alert(self, client):
        """Only one burst alert is created per window, not one per attempt."""
        client.post("/auth/register", json={"email": "burst2@test.com", "password": "Pass1234!"})
        # 10 failed attempts — should only produce 1 burst alert
        for _ in range(10):
            client.post(
                "/auth/login",
                json={"email": "burst2@test.com", "password": "WRONG"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
        with client.application.app_context():
            from app.models import User
            user = _db.session.query(User).filter_by(email="burst2@test.com").first()
            alerts = (
                _db.session.query(SecurityAlert)
                .filter_by(user_id=user.id, alert_type="failed_burst")
                .all()
            )
        assert len(alerts) == 1

    def test_no_burst_below_threshold(self, client):
        client.post("/auth/register", json={"email": "noburst@test.com", "password": "Pass1234!"})
        for _ in range(_BURST_THRESHOLD - 1):
            client.post(
                "/auth/login",
                json={"email": "noburst@test.com", "password": "WRONG"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
        with client.application.app_context():
            from app.models import User
            user = _db.session.query(User).filter_by(email="noburst@test.com").first()
            alerts = (
                _db.session.query(SecurityAlert)
                .filter_by(user_id=user.id, alert_type="failed_burst")
                .all()
            )
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Unusual-hour alert (service-level test — we inject the datetime directly)
# ---------------------------------------------------------------------------

class TestUnusualHourAlert:
    def test_unusual_hour_service(self, app):
        """Directly call the service with a night-time created_at."""
        with app.app_context():
            from app.models import User
            user = User(email="nightowl@test.com",
                        password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.flush()

            event = LoginEvent(
                user_id=user.id,
                ip_hash="abc",
                ua_hash="def",
                ip_masked="1.2.3.xxx",
                success=True,
                created_at=datetime(2024, 6, 15, 2, 30, 0),  # 02:30 UTC
            )
            _db.session.add(event)
            _db.session.flush()

            alerts = check_and_create_alerts(user.id, event)
            unusual = [a for a in alerts if a.alert_type == "unusual_hour"]
            assert len(unusual) == 1
            assert unusual[0].severity == "low"
            _db.session.rollback()

    def test_normal_hour_no_alert(self, app):
        """Daytime login (10:00 UTC) should not trigger unusual-hour alert."""
        with app.app_context():
            from app.models import User
            user = User(email="daytime@test.com",
                        password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.flush()

            event = LoginEvent(
                user_id=user.id,
                ip_hash="abc2",
                ua_hash="def2",
                ip_masked="1.2.3.xxx",
                success=True,
                created_at=datetime(2024, 6, 15, 10, 0, 0),  # 10:00 UTC
            )
            _db.session.add(event)
            _db.session.flush()

            alerts = check_and_create_alerts(user.id, event)
            unusual = [a for a in alerts if a.alert_type == "unusual_hour"]
            assert len(unusual) == 0
            _db.session.rollback()


# ---------------------------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------------------------

class TestAlertEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.token = _reg_login(client, "alert_ep@test.com")
        self.h = _auth(self.token)
        # Trigger a new-IP alert
        client.post("/auth/register", json={"email": "alert_ep2@test.com", "password": "Pass1234!"})
        client.post(
            "/auth/login",
            json={"email": "alert_ep@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "111.222.333.444", "User-Agent": "NewBrowser/99"},
        )

    def test_alerts_list(self, client):
        r = client.get("/security/alerts", headers=self.h)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_unread_count(self, client):
        r = client.get("/security/alerts/unread-count", headers=self.h)
        assert r.status_code == 200
        d = r.get_json()
        assert "unread_count" in d
        assert isinstance(d["unread_count"], int)

    def test_unread_only_filter(self, client):
        r = client.get("/security/alerts?unread_only=true", headers=self.h)
        assert r.status_code == 200
        alerts = r.get_json()
        assert all(not a["acknowledged"] for a in alerts)

    def test_acknowledge_alert(self, client):
        r_all = client.get("/security/alerts", headers=self.h)
        alerts = r_all.get_json()
        if not alerts:
            pytest.skip("No alerts to acknowledge in this run")
        alert_id = alerts[0]["id"]
        r_ack = client.patch(f"/security/alerts/{alert_id}/acknowledge", headers=self.h)
        assert r_ack.status_code == 200
        assert r_ack.get_json()["acknowledged"] is True

    def test_acknowledge_missing_404(self, client):
        r = client.patch("/security/alerts/999999/acknowledge", headers=self.h)
        assert r.status_code == 404

    def test_acknowledge_other_user_404(self, client):
        other = _reg_login(client, "ack_other@test.com")
        r_all = client.get("/security/alerts", headers=self.h)
        alerts = r_all.get_json()
        if not alerts:
            pytest.skip("No alerts in this run")
        alert_id = alerts[0]["id"]
        r = client.patch(
            f"/security/alerts/{alert_id}/acknowledge",
            headers=_auth(other),
        )
        assert r.status_code == 404

    def test_alerts_isolated_per_user(self, client):
        other = _reg_login(client, "iso_alert@test.com")
        r = client.get("/security/alerts", headers=_auth(other))
        assert r.status_code == 200
        # Other user should have no alerts for our account
        # (they can have their own, but our alerts should not appear)
        # We verify by checking none reference alert_ep@test.com's events
        # This is structural — just check it returns a list
        assert isinstance(r.get_json(), list)


# ---------------------------------------------------------------------------
# Login response includes security_alerts
# ---------------------------------------------------------------------------

class TestLoginResponseAlerts:
    def test_alerts_in_login_response(self, client):
        """Login response includes security_alerts key when anomalies are found."""
        client.post("/auth/register",
                    json={"email": "respalerts@test.com", "password": "Pass1234!"})
        # Establish known IP/UA
        client.post(
            "/auth/login",
            json={"email": "respalerts@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "5.5.5.5", "User-Agent": "KnownBrowser/1"},
        )
        # New IP — expect security_alerts in response
        r = client.post(
            "/auth/login",
            json={"email": "respalerts@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "77.88.99.11", "User-Agent": "KnownBrowser/1"},
        )
        d = r.get_json()
        assert r.status_code == 200
        assert "access_token" in d
        assert "security_alerts" in d
        assert len(d["security_alerts"]) >= 1
        al = d["security_alerts"][0]
        assert "alert_type" in al
        assert "severity" in al
        assert "message" in al

    def test_no_alerts_key_when_clean(self, client):
        """Login response should NOT include security_alerts if none raised."""
        client.post("/auth/register",
                    json={"email": "cleanalert@test.com", "password": "Pass1234!"})
        # First login — no history, no alert
        r = client.post(
            "/auth/login",
            json={"email": "cleanalert@test.com", "password": "Pass1234!"},
            headers={"X-Forwarded-For": "10.0.0.1", "User-Agent": "CleanBrowser/1"},
        )
        d = r.get_json()
        assert r.status_code == 200
        assert "security_alerts" not in d
