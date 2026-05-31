from datetime import date, timedelta


def test_check_anomalies_empty(client, auth_header):
    r = client.post("/anomalies/check", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["count"] == 0


def test_list_alerts(client, auth_header):
    r = client.get("/anomalies", headers=auth_header)
    assert r.status_code == 200


def test_dismiss_alert_not_found(client, auth_header):
    r = client.patch("/anomalies/9999/dismiss", headers=auth_header)
    assert r.status_code == 404


def test_check_with_recurring_expense(client, auth_header):
    today = date.today().isoformat()
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 50,
            "notes": "Monthly subscription",
            "cadence": "MONTHLY",
            "start_date": today,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": (date.today() + timedelta(days=90)).isoformat()},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post("/anomalies/check", headers=auth_header)
    assert r.status_code == 200
