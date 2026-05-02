import pytest


class _FakeRedis:
    def __init__(self):
        self._data = {}

    def setex(self, key, _ttl, value):
        self._data[key] = value
        return True

    def get(self, key):
        return self._data.get(key)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            removed += int(key in self._data)
            self._data.pop(key, None)
        return removed


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.routes.auth.redis_client", fake)


def _register(client):
    r = client.post("/auth/register", json={"email": "secure@example.com", "password": "password123"})
    assert r.status_code == 201


def _login(client, ip="203.0.113.10", agent="FinMindTest/1.0", password="password123"):
    return client.post(
        "/auth/login",
        json={"email": "secure@example.com", "password": password},
        headers={"X-Forwarded-For": ip, "User-Agent": agent},
    )


def test_login_records_new_ip_and_device_alerts(client):
    _register(client)
    first = _login(client)
    assert first.status_code == 200
    assert first.get_json()["security_alerts"] == []

    second = _login(client, ip="198.51.100.7", agent="DifferentBrowser/2.0")
    assert second.status_code == 200
    alerts = second.get_json()["security_alerts"]
    assert {alert["type"] for alert in alerts} == {"new_ip", "new_device"}

    token = second.get_json()["access_token"]
    listed = client.get("/auth/security/alerts", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert len(listed.get_json()) == 2


def test_failed_login_burst_alerts_on_next_success(client):
    _register(client)
    for _ in range(5):
        r = _login(client, password="wrong")
        assert r.status_code == 401

    success = _login(client)
    assert success.status_code == 200
    alerts = success.get_json()["security_alerts"]
    assert len(alerts) == 1
    assert alerts[0]["type"] == "failed_login_burst"
    assert alerts[0]["severity"] == "high"

    token = success.get_json()["access_token"]
    alert_id = alerts[0]["id"]
    ack = client.post(
        f"/auth/security/alerts/{alert_id}/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ack.status_code == 200
    assert ack.get_json()["acknowledged"] is True
