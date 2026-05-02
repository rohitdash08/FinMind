def test_login_anomaly_alerts(client, auth_header):
    # Initially no alerts
    r = client.get("/security/alerts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Initially no login history
    r = client.get("/security/login-history", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_alerts_mark_read(client, auth_header):
    # Mark read (no-op when no alerts)
    r = client.post("/security/alerts/mark-read", json={}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "alerts marked as read"


def test_alerts_unread_filter(client, auth_header):
    r = client.get("/security/alerts?unread=true", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_login_history_limit(client, auth_header):
    r = client.get("/security/login-history?limit=5", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
