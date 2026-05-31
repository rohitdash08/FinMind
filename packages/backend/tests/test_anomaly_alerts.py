def test_anomaly_alerts_empty(client, auth_header):
    r = client.get("/anomaly-alerts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_anomaly_check_no_recurring(client, auth_header):
    r = client.post("/anomaly-alerts/check", headers=auth_header)
    assert r.status_code == 201
    assert r.get_json() == []


def test_anomaly_detection_with_recurring(client, auth_header):
    create_payload = {
        "amount": 100.0,
        "description": "Netflix Subscription",
        "cadence": "MONTHLY",
        "start_date": "2026-01-01",
    }
    r = client.post("/expenses/recurring", json=create_payload, headers=auth_header)
    assert r.status_code == 201
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-03-01"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/anomaly-alerts/check", headers=auth_header)
    assert r.status_code == 201
    alerts = r.get_json()
    assert isinstance(alerts, list)


def test_anomaly_acknowledge(client, auth_header):
    create_payload = {
        "amount": 50.0,
        "description": "Gym",
        "cadence": "MONTHLY",
        "start_date": "2026-01-01",
    }
    r = client.post("/expenses/recurring", json=create_payload, headers=auth_header)
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-02-01"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/anomaly-alerts/check", headers=auth_header)
    assert r.status_code == 201
    alerts = r.get_json()

    if alerts:
        alert_id = alerts[0]["id"]
        r = client.post(f"/anomaly-alerts/{alert_id}/acknowledge", headers=auth_header)
        assert r.status_code == 200

    r = client.get("/anomaly-alerts", headers=auth_header)
    assert r.status_code == 200
