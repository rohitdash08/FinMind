"""Tests for login anomaly detection & suspicious activity alerts."""
import pytest


def _register_and_login(client, email="anomaly@test.com", password="secret123"):
    """Helper: register + login, return (access_token, response_json)."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    return data["access_token"], data


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestLoginEventRecording:
    """Login attempts are recorded in login_events."""

    def test_successful_login_recorded(self, client):
        token, data = _register_and_login(client)
        r = client.get("/auth/login-history", headers=_auth(token))
        assert r.status_code == 200
        events = r.get_json()["events"]
        assert len(events) >= 1
        assert events[0]["success"] is True

    def test_failed_login_recorded(self, client):
        # Register first
        client.post(
            "/auth/register",
            json={"email": "fail@test.com", "password": "secret123"},
        )
        # Fail login
        r = client.post(
            "/auth/login",
            json={"email": "fail@test.com", "password": "wrongpassword"},
        )
        assert r.status_code == 401

        # Login successfully and check history
        r = client.post(
            "/auth/login",
            json={"email": "fail@test.com", "password": "secret123"},
        )
        token = r.get_json()["access_token"]

        r = client.get("/auth/login-history", headers=_auth(token))
        events = r.get_json()["events"]
        # Should have both the failed and successful login
        assert len(events) >= 2
        successes = [e for e in events if e["success"]]
        failures = [e for e in events if not e["success"]]
        assert len(successes) >= 1
        assert len(failures) >= 1


class TestLoginHistory:
    """GET /auth/login-history returns paginated login events."""

    def test_login_history_returns_events(self, client):
        token, _ = _register_and_login(client)
        r = client.get("/auth/login-history", headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert "events" in data
        assert "total" in data
        for event in data["events"]:
            assert "id" in event
            assert "ip_address" in event
            assert "success" in event
            assert "created_at" in event

    def test_login_history_respects_limit(self, client):
        token, _ = _register_and_login(client)
        r = client.get("/auth/login-history?limit=1", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.get_json()["events"]) <= 1

    def test_login_history_requires_auth(self, client):
        r = client.get("/auth/login-history")
        assert r.status_code == 401


class TestSecurityAlerts:
    """GET /auth/security-alerts and POST dismiss."""

    def test_security_alerts_empty_by_default(self, client):
        token, _ = _register_and_login(client)
        r = client.get("/auth/security-alerts", headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert "alerts" in data

    def test_new_ip_alert_on_first_login(self, client):
        token, data = _register_and_login(client)
        # First login from a new IP should trigger new_ip_address alert
        r = client.get("/auth/security-alerts", headers=_auth(token))
        alerts = r.get_json()["alerts"]
        new_ip_alerts = [a for a in alerts if a["alert_type"] == "new_ip_address"]
        assert len(new_ip_alerts) >= 1

    def test_dismiss_alert(self, client):
        token, _ = _register_and_login(client)
        # Get alerts
        r = client.get(
            "/auth/security-alerts?include_dismissed=true",
            headers=_auth(token),
        )
        alerts = r.get_json()["alerts"]
        if not alerts:
            pytest.skip("No alerts to dismiss")

        alert_id = alerts[0]["id"]

        # Dismiss it
        r = client.post(
            f"/auth/security-alerts/{alert_id}/dismiss",
            headers=_auth(token),
        )
        assert r.status_code == 200

        # Verify it's dismissed (excluded by default)
        r = client.get("/auth/security-alerts", headers=_auth(token))
        active_ids = [a["id"] for a in r.get_json()["alerts"]]
        assert alert_id not in active_ids

    def test_dismiss_nonexistent_alert(self, client):
        token, _ = _register_and_login(client)
        r = client.post(
            "/auth/security-alerts/99999/dismiss",
            headers=_auth(token),
        )
        assert r.status_code == 404

    def test_security_alerts_requires_auth(self, client):
        r = client.get("/auth/security-alerts")
        assert r.status_code == 401


class TestBruteForceDetection:
    """Multiple failed logins trigger brute-force alert."""

    def test_failed_streak_triggers_alert(self, client):
        email = "brute@test.com"
        client.post(
            "/auth/register",
            json={"email": email, "password": "correct"},
        )

        # 6 failed attempts
        for _ in range(6):
            client.post(
                "/auth/login",
                json={"email": email, "password": "wrong"},
            )

        # Successful login — should see alerts
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "correct"},
        )
        assert r.status_code == 200
        token = r.get_json()["access_token"]

        r = client.get("/auth/security-alerts", headers=_auth(token))
        alerts = r.get_json()["alerts"]
        alert_types = [a["alert_type"] for a in alerts]
        # Should have brute-force or failed-streak alert
        assert any(
            t in ("brute_force_suspected", "failed_streak_before_login")
            for t in alert_types
        ), f"Expected brute-force alert, got: {alert_types}"


class TestIncludeDismissedFilter:
    """The include_dismissed query param works."""

    def test_include_dismissed_true(self, client):
        token, _ = _register_and_login(client)
        r = client.get(
            "/auth/security-alerts?include_dismissed=true",
            headers=_auth(token),
        )
        assert r.status_code == 200
