from datetime import date, timedelta


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _create_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_expense(client, auth_header, amount, desc, dt, expense_type="EXPENSE", category_id=None):
    payload = {
        "amount": amount,
        "description": desc,
        "date": dt.isoformat(),
        "expense_type": expense_type,
    }
    if category_id:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _create_bill(client, auth_header, name, amount, due_date):
    r = client.post(
        "/bills",
        json={
            "name": name,
            "amount": amount,
            "next_due_date": due_date.isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


def test_weekly_digest_empty(client, auth_header):
    """Digest returns valid structure with zero values when no data."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert "period" in data
    assert "summary" in data
    assert data["summary"]["total_income"] == 0.0
    assert data["summary"]["total_expenses"] == 0.0
    assert data["summary"]["net_flow"] == 0.0
    assert isinstance(data["category_breakdown"], list)
    assert isinstance(data["top_expenses"], list)
    assert isinstance(data["daily_spending"], list)
    assert isinstance(data["upcoming_bills"], list)
    assert isinstance(data["insights"], list)
    assert len(data["insights"]) >= 1


def test_weekly_digest_with_data(client, auth_header):
    """Digest correctly calculates income, expenses, and categories."""
    today = date.today()
    monday = _monday_of(today)

    food_id = _create_category(client, auth_header, "Food")
    transport_id = _create_category(client, auth_header, "Transport")

    _create_expense(client, auth_header, 5000, "Salary", monday, "INCOME")
    _create_expense(client, auth_header, 200, "Groceries", monday, "EXPENSE", food_id)
    _create_expense(client, auth_header, 100, "Bus fare", monday + timedelta(days=1), "EXPENSE", transport_id)
    _create_expense(client, auth_header, 300, "Dinner", monday + timedelta(days=2), "EXPENSE", food_id)

    r = client.get(f"/digest/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["summary"]["total_income"] == 5000.0
    assert data["summary"]["total_expenses"] == 600.0
    assert data["summary"]["net_flow"] == 4400.0

    assert len(data["category_breakdown"]) == 2
    assert data["category_breakdown"][0]["category_name"] == "Food"
    assert data["category_breakdown"][0]["amount"] == 500.0

    assert len(data["top_expenses"]) == 3
    assert data["top_expenses"][0]["amount"] == 300.0

    assert len(data["daily_spending"]) >= 2


def test_weekly_digest_week_over_week_comparison(client, auth_header):
    """Digest shows correct WoW changes."""
    today = date.today()
    this_monday = _monday_of(today)
    last_monday = this_monday - timedelta(days=7)

    _create_expense(client, auth_header, 400, "Last week food", last_monday, "EXPENSE")
    _create_expense(client, auth_header, 600, "This week food", this_monday, "EXPENSE")

    r = client.get(f"/digest/weekly?week={this_monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["summary"]["prev_week_expenses"] == 400.0
    assert data["summary"]["total_expenses"] == 600.0
    assert data["summary"]["expense_change_pct"] == 50.0


def test_weekly_digest_upcoming_bills(client, auth_header):
    """Digest includes bills due within the week."""
    today = date.today()
    monday = _monday_of(today)
    bill_due = monday + timedelta(days=3)

    _create_bill(client, auth_header, "Internet", 49.99, bill_due)
    _create_bill(client, auth_header, "Old bill", 100, monday - timedelta(days=10))

    r = client.get(f"/digest/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert len(data["upcoming_bills"]) == 1
    assert data["upcoming_bills"][0]["name"] == "Internet"


def test_weekly_digest_invalid_date(client, auth_header):
    """Returns 400 for invalid date format."""
    r = client.get("/digest/weekly?week=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_weekly_digest_requires_auth(client):
    """Returns 401 without auth token."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401
