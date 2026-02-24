"""Tests for reminder reliability tracking & delivery metrics (#123)."""


def _log(client, auth_header, reminder_id, channel="in_app", status="SENT", latency_ms=None):
    r = client.post("/delivery/log", json={
        "reminder_id": reminder_id, "channel": channel,
        "status": status, "latency_ms": latency_ms,
    }, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


class TestDeliveryLog:
    def test_create_log(self, client, auth_header):
        entry = _log(client, auth_header, 1, "email", "DELIVERED", 120)
        assert entry["reminder_id"] == 1
        assert entry["channel"] == "email"
        assert entry["status"] == "DELIVERED"
        assert entry["latency_ms"] == 120

    def test_missing_reminder_id(self, client, auth_header):
        r = client.post("/delivery/log", json={"channel": "email"}, headers=auth_header)
        assert r.status_code == 400

    def test_log_with_error(self, client, auth_header):
        entry = _log(client, auth_header, 2, "push", "FAILED")
        assert entry["status"] == "FAILED"


class TestMetrics:
    def test_empty_metrics(self, client, auth_header):
        r = client.get("/delivery/metrics", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_deliveries"] == 0
        assert data["success_rate"] == 0.0

    def test_metrics_with_data(self, client, auth_header):
        _log(client, auth_header, 10, "in_app", "DELIVERED", 50)
        _log(client, auth_header, 11, "email", "DELIVERED", 200)
        _log(client, auth_header, 12, "push", "FAILED")

        r = client.get("/delivery/metrics", headers=auth_header)
        data = r.get_json()
        assert data["total_deliveries"] == 3
        assert data["by_status"]["DELIVERED"] == 2
        assert data["by_status"]["FAILED"] == 1
        assert data["success_rate"] > 60

    def test_metrics_custom_days(self, client, auth_header):
        r = client.get("/delivery/metrics?days=7", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["period_days"] == 7


class TestHistory:
    def test_history(self, client, auth_header):
        _log(client, auth_header, 20, "in_app", "SENT")
        _log(client, auth_header, 20, "in_app", "DELIVERED", 100)

        r = client.get("/delivery/history?reminder_id=20", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 2

    def test_history_all(self, client, auth_header):
        _log(client, auth_header, 30, "email", "SENT")
        r = client.get("/delivery/history", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) >= 1
