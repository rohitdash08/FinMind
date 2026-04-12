"""Tests for the weekly digest endpoint (GET /digest/weekly)."""

from datetime import date, timedelta


def _current_week_str():
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _add_expense(client, auth_header, amount, description, spent_at, category_id=None):
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at,
        "expense_type": "EXPENSE",
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


# 1. Unauthenticated request returns 401
def test_digest_requires_auth(client):
    r = client.get("/digest/weekly")
    assert r.status_code in (401, 422)


# 2. Empty week returns zeroes
def test_digest_empty_week(client, auth_header):
    r = client.get(f"/digest/weekly?week={_current_week_str()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 0
    assert data["category_breakdown"] == []
    assert data["week_over_week_change"] == 0.0
    assert data["transaction_count"] == 0
    assert isinstance(data["trends"], list)
    assert isinstance(data["insights"], list)


# 3. Populated week returns correct aggregates
def test_digest_with_expenses(client, auth_header):
    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso.year, iso.week, 1)

    _add_expense(client, auth_header, 50.00, "Lunch", monday.isoformat())
    _add_expense(client, auth_header, 30.00, "Coffee", monday.isoformat())
    _add_expense(
        client, auth_header, 20.00, "Snack",
        (monday + timedelta(days=2)).isoformat(),
    )

    week = f"{iso.year}-W{iso.week:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 100.0
    assert data["transaction_count"] == 3
    assert data["week"] == week
    assert "start_date" in data
    assert "end_date" in data


# 4. Category breakdown is correct
def test_digest_category_breakdown(client, auth_header):
    cat = _create_category(client, auth_header, "Food")
    cat_id = cat["id"]

    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso.year, iso.week, 1)

    _add_expense(
        client, auth_header, 60.00, "Groceries",
        monday.isoformat(), category_id=cat_id,
    )
    _add_expense(
        client, auth_header, 40.00, "Transport",
        monday.isoformat(),
    )

    week = f"{iso.year}-W{iso.week:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    breakdown = data["category_breakdown"]
    assert len(breakdown) >= 1
    food = next((c for c in breakdown if c["category_name"] == "Food"), None)
    assert food is not None
    assert food["amount"] == 60.0


# 5. Week-over-week comparison
def test_digest_week_over_week(client, auth_header):
    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso.year, iso.week, 1)
    prev_monday = monday - timedelta(days=7)

    _add_expense(
        client, auth_header, 100.00, "Last week spend",
        prev_monday.isoformat(),
    )
    _add_expense(
        client, auth_header, 150.00, "This week spend",
        monday.isoformat(),
    )

    week = f"{iso.year}-W{iso.week:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 150.0
    assert data["previous_week_total"] == 100.0
    assert data["week_over_week_change"] == 50.0


# 6. Invalid week format returns 400
def test_digest_invalid_week_format(client, auth_header):
    r = client.get("/digest/weekly?week=bad-format", headers=auth_header)
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data


# 7. Defaults to current week when no param
def test_digest_defaults_to_current_week(client, auth_header):
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["week"] == _current_week_str()


# 8. Trends and insights are populated
def test_digest_trends_and_insights(client, auth_header):
    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso.year, iso.week, 1)

    _add_expense(client, auth_header, 200.00, "Big purchase", monday.isoformat())

    week = f"{iso.year}-W{iso.week:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["trends"]) >= 1
    assert len(data["insights"]) >= 1
    assert any("spending" in t.lower() or "category" in t.lower() for t in data["trends"])
