import datetime


def test_categories_crud_flow(client, auth_header):
    # Initially empty
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create category without budget
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    c1 = r.get_json()
    assert c1["name"] == "Food"
    assert c1["budget"] is None
    assert c1["budget_currency"] == "INR"  # Defaults to user's preferred currency

    # Create category with budget
    r = client.post(
        "/categories", json={"name": "Transport", "budget": 100.0, "budget_currency": "USD"}, headers=auth_header
    )
    assert r.status_code == 201
    c2 = r.get_json()
    assert c2["name"] == "Transport"
    assert c2["budget"] == 100.0
    assert c2["budget_currency"] == "USD"
    assert c2["current_month_spend"] == 0.0

    # Duplicate create should 409
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 409

    # List should have 2
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    assert any(c["id"] == c1["id"] for c in items)
    assert any(c["id"] == c2["id"] for c in items)

    # Update category (name and budget)
    r = client.patch(
        f"/categories/{c1['id']}",
        json={"name": "Groceries", "budget": 500.0, "budget_currency": "EUR"},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated_c1 = r.get_json()
    assert updated_c1["name"] == "Groceries"
    assert updated_c1["budget"] == 500.0
    assert updated_c1["budget_currency"] == "EUR"

    # Get single category
    r = client.get(f"/categories/{c1['id']}", headers=auth_header)
    assert r.status_code == 200
    got_c1 = r.get_json()
    assert got_c1["name"] == "Groceries"
    assert got_c1["budget"] == 500.0

    # Delete category 1
    r = client.delete(f"/categories/{c1['id']}", headers=auth_header)
    assert r.status_code == 200

    # List should have 1 (category 2)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert any(c["id"] == c2["id"] for c in items)

    # Delete category 2
    r = client.delete(f"/categories/{c2['id']}", headers=auth_header)
    assert r.status_code == 200

    # List should be empty again
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_category_overspend_calculation(client, auth_header):
    user_pref_currency = "INR" # Default from conftest.py
    # Ensure user's preferred currency is INR
    r = client.patch(
        "/auth/me", json={"preferred_currency": user_pref_currency}, headers=auth_header
    )
    assert r.status_code == 200

    # Create category with budget in user's preferred currency
    r = client.post(
        "/categories", json={"name": "Monthly Spend", "budget": 1000.0}, headers=auth_header
    )
    assert r.status_code == 201
    category = r.get_json()
    category_id = category["id"]
    assert category["budget"] == 1000.0
    assert category["budget_currency"] == user_pref_currency
    assert category["current_month_spend"] == 0.0

    # Create bills for this category for the current month in the same currency
    today = datetime.date.today()
    this_month_due_date = today.isoformat()
    last_month_due_date = (today.replace(day=1) - datetime.timedelta(days=1)).isoformat() # Last day of previous month
    next_month_due_date = (today.replace(day=28) + datetime.timedelta(days=5)).isoformat() # Some day next month

    # Bill 1: Current month, matching currency
    r = client.post(
        "/bills",
        json={
            "name": "Coffee", "amount": 150.0, "currency": user_pref_currency,
            "next_due_date": this_month_due_date, "cadence": "MONTHLY",
            "category_id": category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Bill 2: Current month, matching currency
    r = client.post(
        "/bills",
        json={
            "name": "Lunch", "amount": 300.0, "currency": user_pref_currency,
            "next_due_date": this_month_due_date, "cadence": "MONTHLY",
            "category_id": category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Bill 3: Current month, DIFFERENT currency (should not be included in spend)
    r = client.post(
        "/bills",
        json={
            "name": "Foreign Item", "amount": 50.0, "currency": "USD",
            "next_due_date": this_month_due_date, "cadence": "MONTHLY",
            "category_id": category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Bill 4: Last month (should not be included in spend)
    r = client.post(
        "/bills",
        json={
            "name": "Old Bill", "amount": 200.0, "currency": user_pref_currency,
            "next_due_date": last_month_due_date, "cadence": "MONTHLY",
            "category_id": category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Bill 5: Next month (should not be included in spend)
    r = client.post(
        "/bills",
        json={
            "name": "Future Bill", "amount": 100.0, "currency": user_pref_currency,
            "next_due_date": next_month_due_date, "cadence": "MONTHLY",
            "category_id": category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Retrieve categories and check current_month_spend
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    categories = r.get_json()
    updated_category = next(c for c in categories if c["id"] == category_id)

    # Expected spend: 150 (Coffee) + 300 (Lunch) = 450.0
    # Bill 3 (USD) is ignored, Bill 4 (last month) is ignored, Bill 5 (next month) is ignored.
    assert updated_category["current_month_spend"] == 450.0
    assert updated_category["budget"] == 1000.0

    # Retrieve single category and check current_month_spend
    r = client.get(f"/categories/{category_id}", headers=auth_header)
    assert r.status_code == 200
    single_category = r.get_json()
    assert single_category["current_month_spend"] == 450.0

    # Test category with no budget_currency explicitly set
    r = client.post(
        "/categories", json={"name": "Unbudgeted Spend"}, headers=auth_header
    )
    assert r.status_code == 201
    unbudgeted_category = r.get_json()
    unbudgeted_category_id = unbudgeted_category["id"]

    # Bill for unbudgeted category, mixed currency
    r = client.post(
        "/bills",
        json={
            "name": "Mixed Currency Bill", "amount": 200.0, "currency": "USD",
            "next_due_date": this_month_due_date, "cadence": "MONTHLY",
            "category_id": unbudgeted_category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Mixed Currency Bill 2", "amount": 100.0, "currency": "INR",
            "next_due_date": this_month_due_date, "cadence": "MONTHLY",
            "category_id": unbudgeted_category_id
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/categories/{unbudgeted_category_id}", headers=auth_header)
    assert r.status_code == 200
    fetched_unbudgeted = r.get_json()
    # When budget_currency is None, all bills linked to the category for the month are summed
    assert fetched_unbudgeted["current_month_spend"] == 300.0

    # Delete category and verify bills are disassociated (category_id set to NULL)
    r = client.delete(f"/categories/{category_id}", headers=auth_header)
    assert r.status_code == 200

    # Check if bills previously linked to category_id now have category_id = null
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    bills = r.get_json()
    for bill in bills:
        if bill["name"] in ["Coffee", "Lunch", "Foreign Item", "Old Bill", "Future Bill"]:
            assert bill["category_id"] is None

