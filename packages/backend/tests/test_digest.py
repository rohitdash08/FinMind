from datetime import date, timedelta


def _create_expense(client, auth_header, amount=10.0, description="Coffee", exp_date=None, expense_type="EXPENSE"):
    d = exp_date or date.today().isoformat()
    r = client.post(
        "/expenses",
        json={"amount": amount, "description": description, "date": d, "expense_type": expense_type},
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


def test_weekly_digest_returns_summary(client, auth_header):
    today = date.today()
    _create_expense(client, auth_header, amount=50.0, description="Groceries", exp_date=today.isoformat())
    _create_expense(client, auth_header, amount=100.0, description="Salary", exp_date=today.isoformat(), expense_type="INCOME")

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "period" in data
    assert "summary" in data
    assert "category_breakdown" in data
    assert "spending_trend" in data
    assert "top_merchants" in data
    assert "upcoming_bills" in data
    assert "insights" in data
    assert data["summary"]["total_expenses"] == 50.0
    assert data["summary"]["total_income"] == 100.0
    assert data["summary"]["net_flow"] == 50.0


def test_weekly_digest_with_custom_week_start(client, auth_header):
    week_start = date(2026, 1, 5)
    _create_expense(client, auth_header, amount=25.0, description="Lunch", exp_date=week_start.isoformat())

    r = client.get(f"/digest/weekly?week_start={week_start.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period"]["week_start"] == week_start.isoformat()
    assert data["period"]["week_end"] == (week_start + timedelta(days=6)).isoformat()


def test_weekly_digest_adjusts_non_monday_start(client, auth_header):
    wednesday = date(2026, 1, 8)
    monday = wednesday - timedelta(days=wednesday.weekday())
    _create_expense(client, auth_header, amount=30.0, description="Dinner", exp_date=wednesday.isoformat())

    r = client.get(f"/digest/weekly?week_start={wednesday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period"]["week_start"] == monday.isoformat()


def test_weekly_digest_invalid_week_start(client, auth_header):
    r = client.get("/digest/weekly?week_start=not-a-date", headers=auth_header)
    assert r.status_code == 400


def test_weekly_digest_spending_trend(client, auth_header):
    today = date.today()
    prev_week = today - timedelta(weeks=1)
    _create_expense(client, auth_header, amount=40.0, description="Current week", exp_date=today.isoformat())
    _create_expense(client, auth_header, amount=20.0, description="Last week", exp_date=prev_week.isoformat())

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    trend = data["spending_trend"]
    assert "current_week_expenses" in trend
    assert "previous_week_expenses" in trend
    assert "week_over_week_change_pct" in trend
    assert "direction" in trend


def test_weekly_digest_insights_generated(client, auth_header):
    today = date.today()
    _create_expense(client, auth_header, amount=500.0, description="Income", exp_date=today.isoformat(), expense_type="INCOME")
    _create_expense(client, auth_header, amount=50.0, description="Small expense", exp_date=today.isoformat())

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data["insights"], list)
    assert len(data["insights"]) > 0
