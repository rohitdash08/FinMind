def test_login_anomaly_alerts_on_new_ip_and_user_agent(client):
    email = "anomaly@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "203.0.113.10", "User-Agent": "FinMind iOS"},
    )
    assert r.status_code == 200
    assert "suspicious_activity_alert" not in r.get_json()

    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": "198.51.100.25", "User-Agent": "FinMind Web"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["suspicious_activity_alert"]["reason"] == "new IP address, new device or browser"
    access = data["access_token"]

    r = client.get("/auth/login-activity", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    events = r.get_json()["events"]
    assert events[0]["anomaly"] is True
    assert events[0]["ip_address"] == "198.51.100.25"
    assert events[0]["success"] is True


def test_failed_login_is_recorded_without_alert(client):
    email = "failed-login@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": "wrong"})
    assert r.status_code == 401

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]

    r = client.get("/auth/login-activity", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    events = r.get_json()["events"]
    assert any(event["success"] is False for event in events)
