from datetime import date, timedelta


def _monday_of(d):
    """Return the Monday of the ISO week containing *d*."""
    return d - timedelta(days=d.weekday())


def _seed_expense(client, auth_header, amount, desc, spent_at, expense_type="EXPENSE", category_id=None):
    """Helper to create an expense via the API."""
    payload = {
        "amount": amount,
        "description": desc,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_weekly_digest_returns_current_week(client, auth_header):
    """GET /digest/weekly returns a digest for the current week."""
    today = date.today()
    _seed_expense(client, auth_header, 1000, "Salary", today, expense_type="INCOME")
    _seed_expense(client, auth_header, 200, "Groceries", today, expense_type="EXPENSE")

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert "week_start" in payload
    assert "week_end" in payload
    assert payload["total_income"] >= 1000
    assert payload["total_expenses"] >= 200
    assert "net_flow" in payload
    assert "top_categories" in payload
    assert "trends" in payload
    assert "ai_insights" in payload


def test_weekly_digest_by_date(client, auth_header):
    """GET /digest/weekly/<date> returns digest for the week containing that date."""
    today = date.today()
    _seed_expense(client, auth_header, 500, "Freelance", today, expense_type="INCOME")
    _seed_expense(client, auth_header, 100, "Coffee", today, expense_type="EXPENSE")

    r = client.get(f"/digest/weekly/{today.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    monday = _monday_of(today)
    assert payload["week_start"] == monday.isoformat()
    assert payload["total_income"] >= 500
    assert payload["total_expenses"] >= 100


def test_weekly_digest_invalid_date_returns_400(client, auth_header):
    """GET /digest/weekly/<bad-date> returns 400."""
    r = client.get("/digest/weekly/not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_weekly_digest_trends_comparison(client, auth_header):
    """Trends should compare current vs previous week."""
    today = date.today()
    monday = _monday_of(today)
    prev_monday = monday - timedelta(days=7)

    # Previous week: spend 300
    _seed_expense(client, auth_header, 300, "Prev week food", prev_monday, expense_type="EXPENSE")

    # Current week: spend 150
    _seed_expense(client, auth_header, 150, "Curr week food", monday, expense_type="EXPENSE")

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    trends = payload["trends"]
    assert "expense_change_pct" in trends
    # Expenses decreased from 300 to 150 = -50%
    assert trends["expense_change_pct"] == -50.0
    assert trends["expense_trend"] == "down"
    assert trends["previous_week_expenses"] == 300.0


def test_weekly_digest_top_categories(client, auth_header):
    """Top categories should list spending by category with percentages."""
    today = date.today()

    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    assert r.status_code == 201
    transport_id = r.get_json()["id"]

    _seed_expense(client, auth_header, 400, "Groceries", today, category_id=food_id)
    _seed_expense(client, auth_header, 100, "Bus pass", today, category_id=transport_id)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    cats = payload["top_categories"]
    assert isinstance(cats, list)
    assert len(cats) >= 2

    # Food should be first (highest spend)
    assert cats[0]["category_name"] == "Food"
    assert cats[0]["amount"] == 400.0
    # Share should be 80% (400 out of 500)
    assert cats[0]["share_pct"] == 80.0


def test_digest_history_returns_past_digests(client, auth_header):
    """GET /digest/history returns previously generated digests."""
    today = date.today()
    monday = _monday_of(today)
    prev_monday = monday - timedelta(days=7)

    _seed_expense(client, auth_header, 100, "Week 1", prev_monday)
    _seed_expense(client, auth_header, 200, "Week 2", monday)

    # Generate digests for both weeks
    client.get(f"/digest/weekly/{prev_monday.isoformat()}", headers=auth_header)
    client.get(f"/digest/weekly/{monday.isoformat()}", headers=auth_header)

    r = client.get("/digest/history", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()

    assert isinstance(history, list)
    assert len(history) >= 2
    # Most recent first
    assert history[0]["week_start"] >= history[1]["week_start"]


def test_digest_history_respects_limit(client, auth_header):
    """GET /digest/history?limit=1 returns only one digest."""
    today = date.today()
    _seed_expense(client, auth_header, 50, "Expense", today)

    # Generate current week digest
    client.get("/digest/weekly", headers=auth_header)

    r = client.get("/digest/history?limit=1", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()
    assert len(history) <= 1


def test_force_generate_creates_new_digest(client, auth_header):
    """POST /digest/generate should regenerate the digest."""
    today = date.today()
    _seed_expense(client, auth_header, 500, "Initial", today, expense_type="INCOME")

    r = client.post("/digest/generate", headers=auth_header)
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["total_income"] >= 500

    # Add more income and force regenerate
    _seed_expense(client, auth_header, 300, "Extra", today, expense_type="INCOME")
    r = client.post("/digest/generate", headers=auth_header)
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["total_income"] >= 800


def test_digest_requires_auth(client):
    """All digest endpoints should require JWT authentication."""
    endpoints = [
        ("GET", "/digest/weekly"),
        ("GET", "/digest/weekly/2026-01-01"),
        ("GET", "/digest/history"),
        ("POST", "/digest/generate"),
    ]
    for method, path in endpoints:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path)
        assert r.status_code in (401, 422), f"{method} {path} should require auth"


def test_digest_caching_returns_same_result(client, auth_header):
    """Repeated GET calls should return the same digest (from cache/DB)."""
    today = date.today()
    _seed_expense(client, auth_header, 250, "Cached test", today)

    r1 = client.get("/digest/weekly", headers=auth_header)
    assert r1.status_code == 200
    d1 = r1.get_json()

    r2 = client.get("/digest/weekly", headers=auth_header)
    assert r2.status_code == 200
    d2 = r2.get_json()

    assert d1["total_expenses"] == d2["total_expenses"]
    assert d1["week_start"] == d2["week_start"]


def test_digest_net_flow_calculation(client, auth_header):
    """Net flow should equal income minus expenses."""
    today = date.today()
    _seed_expense(client, auth_header, 1000, "Salary", today, expense_type="INCOME")
    _seed_expense(client, auth_header, 350, "Rent", today, expense_type="EXPENSE")
    _seed_expense(client, auth_header, 150, "Utils", today, expense_type="EXPENSE")

    r = client.post("/digest/generate", headers=auth_header)
    assert r.status_code == 201
    payload = r.get_json()

    expected_net = payload["total_income"] - payload["total_expenses"]
    assert abs(payload["net_flow"] - expected_net) < 0.01


def test_digest_empty_week(client, auth_header):
    """A week with no data should still return a valid digest."""
    # Request a far-past week with no data
    r = client.get("/digest/weekly/2020-01-06", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_income"] == 0
    assert payload["total_expenses"] == 0
    assert payload["net_flow"] == 0
