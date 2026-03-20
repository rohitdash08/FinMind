from datetime import date, timedelta


def test_heatmap_returns_empty_when_no_expenses(client, auth_header):
    r = client.get("/expenses/heatmap", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_heatmap_returns_aggregated_daily_totals(client, auth_header):
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Create two expenses on the same day and one on another day
    client.post(
        "/expenses",
        json={"amount": 10.00, "description": "Coffee", "date": today},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 15.50, "description": "Lunch", "date": today},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 5.00, "description": "Snack", "date": yesterday},
        headers=auth_header,
    )

    r = client.get("/expenses/heatmap?months=1", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)

    lookup = {entry["date"]: entry["amount"] for entry in data}
    assert lookup[today] == 25.50
    assert lookup[yesterday] == 5.00


def test_heatmap_requires_auth(client):
    r = client.get("/expenses/heatmap")
    assert r.status_code == 401


def test_heatmap_invalid_months_param(client, auth_header):
    r = client.get("/expenses/heatmap?months=abc", headers=auth_header)
    assert r.status_code == 400
    assert "invalid" in r.get_json()["error"].lower()
