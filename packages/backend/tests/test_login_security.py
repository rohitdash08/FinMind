import pytest


@pytest.fixture(autouse=True)
def _skip_refresh_session_redis(monkeypatch):
    monkeypatch.setattr("app.routes.auth._store_refresh_session", lambda *_args: None)


def _register(client, email="security@example.com", password="secret123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)


def _login(client, email, password, ip="10.0.0.1", user_agent="FinMindTest/1.0"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": user_agent},
        environ_overrides={"REMOTE_ADDR": ip},
    )


def test_login_from_new_ip_and_device_creates_security_alerts(client):
    email = "alerts@example.com"
    password = "secret123"
    _register(client, email, password)

    first = _login(client, email, password, ip="10.0.0.1", user_agent="KnownBrowser/1")
    assert first.status_code == 200
    assert first.get_json()["security_alerts"] == []

    second = _login(
        client, email, password, ip="203.0.113.9", user_agent="NewBrowser/2"
    )
    assert second.status_code == 200
    payload = second.get_json()
    alert_types = {alert["alert_type"] for alert in payload["security_alerts"]}
    assert {"new_ip", "new_device"}.issubset(alert_types)

    access = payload["access_token"]
    history = client.get(
        "/auth/login-history",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert history.status_code == 200
    events = history.get_json()["events"]
    assert len(events) == 2
    assert events[0]["ip_address"] == "203.0.113.9"
    assert "new_ip" in events[0]["suspicion_reasons"]

    alerts = client.get(
        "/auth/security-alerts",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert alerts.status_code == 200
    assert alerts.get_json()["unread_count"] == len(payload["security_alerts"])


def test_failed_login_burst_is_reported_on_next_successful_login(client):
    email = "burst@example.com"
    password = "secret123"
    _register(client, email, password)

    baseline = _login(client, email, password, ip="10.0.0.2", user_agent="Browser/1")
    assert baseline.status_code == 200

    for _ in range(5):
        failed = _login(
            client, email, "wrong-password", ip="10.0.0.2", user_agent="Browser/1"
        )
        assert failed.status_code == 401

    success = _login(client, email, password, ip="10.0.0.2", user_agent="Browser/1")
    assert success.status_code == 200
    payload = success.get_json()
    assert any(
        alert["alert_type"] == "failed_login_burst"
        for alert in payload["security_alerts"]
    )


def test_security_alerts_can_be_acknowledged(client):
    email = "ack@example.com"
    password = "secret123"
    _register(client, email, password)

    _login(client, email, password, ip="10.0.0.3", user_agent="Browser/1")
    login = _login(client, email, password, ip="198.51.100.7", user_agent="Browser/1")
    assert login.status_code == 200
    access = login.get_json()["access_token"]

    alerts = client.get(
        "/auth/security-alerts",
        headers={"Authorization": f"Bearer {access}"},
    ).get_json()["alerts"]
    assert alerts

    response = client.post(
        f"/auth/security-alerts/{alerts[0]['id']}/acknowledge",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    assert response.get_json()["acknowledged"] is True

    refreshed = client.get(
        "/auth/security-alerts",
        headers={"Authorization": f"Bearer {access}"},
    ).get_json()
    assert refreshed["unread_count"] == len(alerts) - 1
