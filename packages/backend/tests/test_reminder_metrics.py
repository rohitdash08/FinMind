from datetime import datetime, timedelta


def test_reminder_metrics_requires_auth(client):
    r = client.get("/reminder-metrics")
    assert r.status_code == 401


def test_reminder_metrics_empty(client, auth_header):
    r = client.get("/reminder-metrics", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_sent"] == 0
    assert data["total_pending"] == 0
    assert data["delivery_rate"] == 0.0
    assert data["failed_count"] == 0
    assert data["avg_delay_seconds"] == 0.0


def test_reminder_metrics_with_data(client, auth_header):
    # Create a reminder
    r = client.post(
        "/reminders",
        json={
            "message": "Pay electricity",
            "send_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/reminder-metrics", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_pending"] >= 1


def test_reminder_history_requires_auth(client):
    r = client.get("/reminder-metrics/history")
    assert r.status_code == 401


def test_reminder_history_empty(client, auth_header):
    r = client.get("/reminder-metrics/history", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_reminder_history_with_data(client, auth_header):
    # Create a reminder
    r = client.post(
        "/reminders",
        json={
            "message": "Test history",
            "send_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/reminder-metrics/history", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 1
    assert data[0]["message"] == "Test history"
    assert data[0]["status"] == "pending"
