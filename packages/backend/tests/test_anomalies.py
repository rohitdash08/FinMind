"""Tests for recurring transaction anomaly alerts."""

from datetime import date, timedelta


def _add_expense(client, auth_header, amount, desc, spent_at=None):
    payload = {"amount": amount, "description": desc, "expense_type": "EXPENSE"}
    if spent_at:
        payload["date"] = spent_at
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


# 1. Auth required
def test_anomalies_requires_auth(client):
    r = client.get("/anomalies")
    assert r.status_code in (401, 422)


# 2. Empty alerts
def test_empty_alerts(client, auth_header):
    r = client.get("/anomalies", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


# 3. Scan with no history returns no alerts
def test_scan_no_history(client, auth_header):
    r = client.post("/anomalies/scan", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["alerts_created"] == 0


# 4. Large transaction detected
def test_large_transaction_alert(client, auth_header):
    today = date.today()
    two_weeks_ago = today - timedelta(days=14)
    for i in range(5):
        _add_expense(client, auth_header, 20, f"Normal {i}", (two_weeks_ago + timedelta(days=i)).isoformat())
    _add_expense(client, auth_header, 500, "Huge purchase", today.isoformat())
    r = client.post("/anomalies/scan", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["alerts_created"] >= 1
    assert any(a["alert_type"] == "large_transaction" for a in data["alerts"])


# 5. Acknowledge alert
def test_acknowledge_alert(client, auth_header):
    today = date.today()
    two_weeks_ago = today - timedelta(days=14)
    for i in range(3):
        _add_expense(client, auth_header, 10, f"Small {i}", (two_weeks_ago + timedelta(days=i)).isoformat())
    _add_expense(client, auth_header, 300, "Big one", today.isoformat())
    client.post("/anomalies/scan", headers=auth_header)
    r = client.get("/anomalies", headers=auth_header)
    alerts = r.get_json()
    if alerts:
        alert_id = alerts[0]["id"]
        r = client.post(f"/anomalies/{alert_id}/acknowledge", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["acknowledged"] is True


# 6. Filter unacknowledged
def test_filter_unacknowledged(client, auth_header):
    r = client.get("/anomalies?unacknowledged=true", headers=auth_header)
    assert r.status_code == 200


# 7. No duplicate alerts on rescan
def test_no_duplicate_alerts(client, auth_header):
    today = date.today()
    two_weeks_ago = today - timedelta(days=14)
    for i in range(3):
        _add_expense(client, auth_header, 15, f"Hist {i}", (two_weeks_ago + timedelta(days=i)).isoformat())
    _add_expense(client, auth_header, 400, "Big", today.isoformat())
    r1 = client.post("/anomalies/scan", headers=auth_header)
    count1 = r1.get_json()["alerts_created"]
    r2 = client.post("/anomalies/scan", headers=auth_header)
    count2 = r2.get_json()["alerts_created"]
    assert count2 == 0  # no duplicates


# 8. Alert not found returns 404
def test_acknowledge_not_found(client, auth_header):
    r = client.post("/anomalies/99999/acknowledge", headers=auth_header)
    assert r.status_code == 404
