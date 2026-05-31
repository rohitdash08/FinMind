def test_daily_spending_empty(client, auth_header):
    r = client.get("/insights/heatmap/daily?year=2026", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_daily_spending_with_data(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 50, "description": "Test", "date": "2026-02-10"},
        headers=auth_header,
    )
    r = client.get(
        "/insights/heatmap/daily?year=2026&month=2", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["amount"] == 50


def test_weekly_spending(client, auth_header):
    r = client.get("/insights/heatmap/weekly?year=2026", headers=auth_header)
    assert r.status_code == 200


def test_monthly_spending(client, auth_header):
    r = client.get("/insights/heatmap/monthly?year=2026", headers=auth_header)
    assert r.status_code == 200


def test_category_heatmap(client, auth_header):
    r = client.get("/insights/heatmap/by-category?year=2026", headers=auth_header)
    assert r.status_code == 200


def test_spending_density(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 100, "description": "Test", "date": "2026-02-10"},
        headers=auth_header,
    )
    r = client.get("/insights/heatmap/density?year=2026", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 100
    assert data["days"] == 1
