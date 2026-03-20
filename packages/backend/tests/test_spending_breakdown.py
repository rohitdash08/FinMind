"""Tests for the GET /expenses/spending-breakdown endpoint."""


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    for cat in r.get_json():
        if cat["name"] == name:
            return cat["id"]
    raise AssertionError(f"category '{name}' not found after creation")


def _add_expense(client, auth_header, amount, category_id, date_str):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": f"Expense {amount}",
            "category_id": category_id,
            "date": date_str,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


def test_spending_breakdown_empty(client, auth_header):
    """With no expenses the endpoint returns zeroed buckets."""
    r = client.get("/expenses/spending-breakdown", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period_total"] == 0
    assert data["essential"]["total"] == 0
    assert data["discretionary"]["total"] == 0
    assert data["uncategorized"]["total"] == 0


def test_spending_breakdown_classifies_categories(client, auth_header):
    """Expenses are correctly classified by category keyword matching."""
    grocery_id = _create_category(client, auth_header, "Groceries")
    dining_id = _create_category(client, auth_header, "Dining Out")
    misc_id = _create_category(client, auth_header, "Miscellaneous")

    _add_expense(client, auth_header, 100.00, grocery_id, "2026-02-01")
    _add_expense(client, auth_header, 50.00, grocery_id, "2026-02-10")
    _add_expense(client, auth_header, 75.00, dining_id, "2026-02-05")
    _add_expense(client, auth_header, 30.00, misc_id, "2026-02-15")

    r = client.get(
        "/expenses/spending-breakdown?from=2026-02-01&to=2026-02-28",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()

    assert data["period_total"] == 255.00
    assert data["essential"]["total"] == 150.00
    assert len(data["essential"]["categories"]) == 1
    assert data["essential"]["categories"][0]["name"] == "Groceries"

    assert data["discretionary"]["total"] == 75.00
    assert len(data["discretionary"]["categories"]) == 1
    assert data["discretionary"]["categories"][0]["name"] == "Dining Out"

    assert data["uncategorized"]["total"] == 30.00
    assert len(data["uncategorized"]["categories"]) == 1
    assert data["uncategorized"]["categories"][0]["name"] == "Miscellaneous"


def test_spending_breakdown_date_filtering(client, auth_header):
    """Only expenses within the from/to range are included."""
    rent_id = _create_category(client, auth_header, "Rent")
    _add_expense(client, auth_header, 1000.00, rent_id, "2026-01-01")
    _add_expense(client, auth_header, 1000.00, rent_id, "2026-02-01")
    _add_expense(client, auth_header, 1000.00, rent_id, "2026-03-01")

    r = client.get(
        "/expenses/spending-breakdown?from=2026-02-01&to=2026-02-28",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["period_total"] == 1000.00
    assert data["essential"]["total"] == 1000.00


def test_spending_breakdown_requires_auth(client):
    """The endpoint requires JWT authentication."""
    r = client.get("/expenses/spending-breakdown")
    assert r.status_code == 401


def test_spending_breakdown_invalid_date(client, auth_header):
    """Invalid date parameters return 400."""
    r = client.get(
        "/expenses/spending-breakdown?from=bad-date",
        headers=auth_header,
    )
    assert r.status_code == 400


def test_spending_breakdown_no_category_expense(client, auth_header):
    """Expenses without a category go into uncategorized."""
    r = client.post(
        "/expenses",
        json={
            "amount": 42.00,
            "description": "Random purchase",
            "date": "2026-02-15",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        "/expenses/spending-breakdown?from=2026-02-01&to=2026-02-28",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["uncategorized"]["total"] == 42.00
    assert data["essential"]["total"] == 0
    assert data["discretionary"]["total"] == 0


def test_spending_breakdown_multiple_essential_keywords(client, auth_header):
    """Multiple essential categories are aggregated correctly."""
    insurance_id = _create_category(client, auth_header, "Health Insurance")
    utilities_id = _create_category(client, auth_header, "Utilities")

    _add_expense(client, auth_header, 200.00, insurance_id, "2026-02-01")
    _add_expense(client, auth_header, 80.00, utilities_id, "2026-02-15")

    r = client.get(
        "/expenses/spending-breakdown?from=2026-02-01&to=2026-02-28",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["essential"]["total"] == 280.00
    # Categories sorted by amount descending
    names = [c["name"] for c in data["essential"]["categories"]]
    assert names == ["Health Insurance", "Utilities"]
