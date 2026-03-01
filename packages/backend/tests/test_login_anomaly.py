"""Tests for login anomaly detection and login history endpoints."""

import json


def _register_and_login(client, email="anomaly@test.com", password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    return data["access_token"], data.get("refresh_token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestLoginHistory:
    def test_login_records_history(self, client):
        access, _ = _register_and_login(client)
        r = client.get("/auth/login-history", headers=_auth(access))
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["success"] is True
        assert "created_at" in item

    def test_login_history_pagination(self, client):
        access, _ = _register_and_login(client)
        # Login a few more times
        for _ in range(3):
            client.post(
                "/auth/login",
                json={"email": "anomaly@test.com", "password": "secret123"},
            )
        r = client.get(
            "/auth/login-history?page=1&per_page=2", headers=_auth(access)
        )
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["items"]) == 2
        assert data["per_page"] == 2

    def test_failed_login_recorded(self, client):
        # Register user first
        client.post(
            "/auth/register",
            json={"email": "fail@test.com", "password": "secret123"},
        )
        # Attempt wrong password
        client.post(
            "/auth/login",
            json={"email": "fail@test.com", "password": "wrong"},
        )
        # Now login successfully
        r = client.post(
            "/auth/login",
            json={"email": "fail@test.com", "password": "secret123"},
        )
        access = r.get_json()["access_token"]
        r = client.get("/auth/login-history", headers=_auth(access))
        items = r.get_json()["items"]
        # Should have both failed and successful entries
        assert any(not i["success"] for i in items)
        assert any(i["success"] for i in items)


class TestAnomalyDetection:
    def test_first_login_flags_new_ip_and_device(self, client):
        """First login should flag new_ip and new_device."""
        client.post(
            "/auth/register",
            json={"email": "newuser@test.com", "password": "secret123"},
        )
        r = client.post(
            "/auth/login",
            json={"email": "newuser@test.com", "password": "secret123"},
            headers={"User-Agent": "TestBrowser/1.0"},
        )
        assert r.status_code == 200
        data = r.get_json()
        warnings = data.get("security_warnings", [])
        assert "new_ip" in warnings
        assert "new_device" in warnings

    def test_second_login_same_env_no_warnings(self, client):
        """Second login from same IP/UA should not flag new_ip/new_device."""
        client.post(
            "/auth/register",
            json={"email": "repeat@test.com", "password": "secret123"},
        )
        # First login
        client.post(
            "/auth/login",
            json={"email": "repeat@test.com", "password": "secret123"},
        )
        # Second login — same IP and UA
        r = client.post(
            "/auth/login",
            json={"email": "repeat@test.com", "password": "secret123"},
        )
        data = r.get_json()
        warnings = data.get("security_warnings", [])
        assert "new_ip" not in warnings
        assert "new_device" not in warnings


class TestSecurityAlerts:
    def test_alerts_created_on_anomaly(self, client):
        client.post(
            "/auth/register",
            json={"email": "alertuser@test.com", "password": "secret123"},
        )
        r = client.post(
            "/auth/login",
            json={"email": "alertuser@test.com", "password": "secret123"},
        )
        access = r.get_json()["access_token"]
        r = client.get("/auth/security-alerts", headers=_auth(access))
        assert r.status_code == 200
        alerts = r.get_json()["items"]
        # First login always triggers new_ip alert
        assert len(alerts) >= 1
        assert any(a["alert_type"] == "new_ip" for a in alerts)

    def test_acknowledge_alert(self, client):
        client.post(
            "/auth/register",
            json={"email": "ack@test.com", "password": "secret123"},
        )
        r = client.post(
            "/auth/login",
            json={"email": "ack@test.com", "password": "secret123"},
        )
        access = r.get_json()["access_token"]
        r = client.get("/auth/security-alerts", headers=_auth(access))
        alert_id = r.get_json()["items"][0]["id"]

        r = client.post(
            f"/auth/security-alerts/{alert_id}/acknowledge",
            headers=_auth(access),
        )
        assert r.status_code == 200

        # Verify acknowledged
        r = client.get("/auth/security-alerts", headers=_auth(access))
        alert = next(
            a for a in r.get_json()["items"] if a["id"] == alert_id
        )
        assert alert["acknowledged"] is True

    def test_acknowledge_other_user_alert_404(self, client):
        # User 1
        client.post(
            "/auth/register",
            json={"email": "user1@test.com", "password": "secret123"},
        )
        r = client.post(
            "/auth/login",
            json={"email": "user1@test.com", "password": "secret123"},
        )
        access1 = r.get_json()["access_token"]
        r = client.get("/auth/security-alerts", headers=_auth(access1))
        alert_id = r.get_json()["items"][0]["id"]

        # User 2
        client.post(
            "/auth/register",
            json={"email": "user2@test.com", "password": "secret123"},
        )
        r = client.post(
            "/auth/login",
            json={"email": "user2@test.com", "password": "secret123"},
        )
        access2 = r.get_json()["access_token"]

        # User 2 tries to ack User 1's alert
        r = client.post(
            f"/auth/security-alerts/{alert_id}/acknowledge",
            headers=_auth(access2),
        )
        assert r.status_code == 404


class TestBruteForceDetection:
    def test_multiple_failures_create_alert(self, client):
        client.post(
            "/auth/register",
            json={"email": "brute@test.com", "password": "secret123"},
        )
        # Trigger 5+ failed attempts
        for _ in range(6):
            client.post(
                "/auth/login",
                json={"email": "brute@test.com", "password": "wrong"},
            )
        # Login successfully
        r = client.post(
            "/auth/login",
            json={"email": "brute@test.com", "password": "secret123"},
        )
        access = r.get_json()["access_token"]
        r = client.get("/auth/security-alerts", headers=_auth(access))
        alerts = r.get_json()["items"]
        assert any(
            a["alert_type"] == "multiple_failed_attempts" for a in alerts
        )
