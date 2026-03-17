from datetime import date, timedelta


def _seed_expenses(client, auth_header, expenses):
    """Helper to create multiple expenses."""
    for exp in expenses:
        r = client.post("/expenses", json=exp, headers=auth_header)
        assert r.status_code == 201, f"Failed to create expense: {r.get_json()}"


def _monday_of(d):
    """Return Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


def _sunday_of(d):
    """Return Sunday of the week containing date d."""
    return _monday_of(d) + timedelta(days=6)


def test_weekly_digest_returns_structure(client, auth_header):
    """Digest endpoint returns proper payload structure even with no data."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Verify top-level keys
    assert "period" in payload
    assert "summary" in payload
    assert "trends" in payload
    assert "category_breakdown" in payload
    assert "daily_spending" in payload
    assert "top_transactions" in payload
    assert "upcoming_bills" in payload
    assert "insights" in payload

    # Verify period structure
    assert "week_start" in payload["period"]
    assert "week_end" in payload["period"]

    # Verify summary structure
    summary = payload["summary"]
    assert "total_income" in summary
    assert "total_expenses" in summary
    assert "net_flow" in summary
    assert "transaction_count" in summary

    # Verify trends structure
    trends = payload["trends"]
    assert "expense_change_pct" in trends
    assert "income_change_pct" in trends
    assert "previous_week_expenses" in trends
    assert "previous_week_income" in trends


def test_weekly_digest_calculates_income_and_expenses(client, auth_header):
    """Digest correctly sums income and expenses for the current week."""
    today = date.today()
    monday = _monday_of(today)

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 5000,
                "description": "Salary",
                "date": monday.isoformat(),
                "expense_type": "INCOME",
            },
            {
                "amount": 200,
                "description": "Groceries",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            {
                "amount": 150,
                "description": "Transport",
                "date": (monday + timedelta(days=1)).isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["total_income"] == 5000.0
    assert payload["summary"]["total_expenses"] == 350.0
    assert payload["summary"]["net_flow"] == 4650.0
    assert payload["summary"]["transaction_count"] == 3


def test_weekly_digest_category_breakdown(client, auth_header):
    """Digest returns correct category breakdown with percentages."""
    today = date.today()
    monday = _monday_of(today)

    # Create categories
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    assert r.status_code == 201
    transport_id = r.get_json()["id"]

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 300,
                "description": "Weekly groceries",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
                "category_id": food_id,
            },
            {
                "amount": 100,
                "description": "Bus pass",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
                "category_id": transport_id,
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    categories = payload["category_breakdown"]
    assert len(categories) == 2
    # Food should be first (highest spend)
    assert categories[0]["category_name"] == "Food"
    assert categories[0]["amount"] == 300.0
    assert categories[0]["share_pct"] == 75.0
    assert categories[1]["category_name"] == "Transport"
    assert categories[1]["amount"] == 100.0
    assert categories[1]["share_pct"] == 25.0


def test_weekly_digest_daily_spending(client, auth_header):
    """Digest returns 7 daily spending entries for the week."""
    today = date.today()
    monday = _monday_of(today)

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 50,
                "description": "Lunch Monday",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            {
                "amount": 75,
                "description": "Lunch Wednesday",
                "date": (monday + timedelta(days=2)).isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    daily = payload["daily_spending"]
    assert len(daily) == 7  # Always 7 days
    assert daily[0]["date"] == monday.isoformat()
    assert daily[0]["amount"] == 50.0
    assert daily[1]["amount"] == 0.0  # Tuesday no spending
    assert daily[2]["amount"] == 75.0  # Wednesday


def test_weekly_digest_top_transactions(client, auth_header):
    """Digest returns top transactions sorted by amount descending."""
    today = date.today()
    monday = _monday_of(today)

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 10,
                "description": "Small purchase",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            {
                "amount": 500,
                "description": "Big purchase",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            {
                "amount": 100,
                "description": "Medium purchase",
                "date": (monday + timedelta(days=1)).isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    top = payload["top_transactions"]
    assert len(top) == 3
    assert top[0]["amount"] == 500.0
    assert top[0]["description"] == "Big purchase"
    assert top[1]["amount"] == 100.0
    assert top[2]["amount"] == 10.0


def test_weekly_digest_week_over_week_trends(client, auth_header):
    """Digest correctly calculates week-over-week trends."""
    today = date.today()
    this_monday = _monday_of(today)
    last_monday = this_monday - timedelta(days=7)

    # Previous week: 200 total expenses
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 200,
                "description": "Last week expense",
                "date": last_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    # Current week: 300 total expenses (50% increase)
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 300,
                "description": "This week expense",
                "date": this_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    trends = payload["trends"]
    assert trends["expense_change_pct"] == 50.0
    assert trends["previous_week_expenses"] == 200.0


def test_weekly_digest_upcoming_bills(client, auth_header):
    """Digest includes bills due in the week following the digest week."""
    today = date.today()
    this_sunday = _sunday_of(today)
    next_monday = this_sunday + timedelta(days=1)
    next_wednesday = next_monday + timedelta(days=2)

    # Create a bill due next week
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": next_wednesday.isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    bills = payload["upcoming_bills"]
    assert len(bills) == 1
    assert bills[0]["name"] == "Internet"
    assert bills[0]["amount"] == 49.99


def test_weekly_digest_insights_generated(client, auth_header):
    """Digest generates at least one insight when there is spending data."""
    today = date.today()
    monday = _monday_of(today)

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 500,
                "description": "Big expense",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert isinstance(payload["insights"], list)
    assert len(payload["insights"]) >= 1


def test_weekly_digest_week_of_param(client, auth_header):
    """Digest supports week_of query parameter for historical weeks."""
    # Seed expense in a specific past week
    past_date = date(2026, 1, 7)  # A Wednesday
    past_monday = _monday_of(past_date)  # 2026-01-05

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 999,
                "description": "Historical expense",
                "date": past_date.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get(
        f"/digest/weekly?week_of={past_date.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["period"]["week_start"] == past_monday.isoformat()
    assert payload["summary"]["total_expenses"] == 999.0


def test_weekly_digest_invalid_date_returns_400(client, auth_header):
    """Invalid week_of parameter returns 400."""
    r = client.get("/digest/weekly?week_of=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "invalid date" in r.get_json()["error"]


def test_weekly_digest_requires_auth(client):
    """Digest endpoint requires authentication."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401


def test_weekly_digest_empty_week(client, auth_header):
    """Digest for a week with no data returns zeroed summary."""
    r = client.get("/digest/weekly?week_of=2020-01-06", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["total_income"] == 0.0
    assert payload["summary"]["total_expenses"] == 0.0
    assert payload["summary"]["net_flow"] == 0.0
    assert payload["summary"]["transaction_count"] == 0
    assert payload["category_breakdown"] == []
    assert payload["top_transactions"] == []
    assert len(payload["daily_spending"]) == 7


def test_weekly_digest_persists_to_database(client, auth_header):
    """Accessing digest endpoint persists the digest record."""
    today = date.today()
    monday = _monday_of(today)

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 100,
                "description": "Test expense",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    # Generate digest
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200

    # Check history
    r = client.get("/digest/weekly/history", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()

    assert history["total"] >= 1
    assert len(history["digests"]) >= 1
    digest = history["digests"][0]
    assert digest["week_start"] == monday.isoformat()
    assert digest["total_expenses"] == 100.0


def test_weekly_digest_history_pagination(client, auth_header):
    """History endpoint supports pagination."""
    # Generate digests for two different weeks
    week1_date = date(2026, 1, 7)  # Week of Jan 5
    week2_date = date(2026, 1, 14)  # Week of Jan 12

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 50,
                "description": "Week 1 expense",
                "date": week1_date.isoformat(),
                "expense_type": "EXPENSE",
            },
            {
                "amount": 75,
                "description": "Week 2 expense",
                "date": week2_date.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    # Generate both digests
    client.get(f"/digest/weekly?week_of={week1_date.isoformat()}", headers=auth_header)
    client.get(f"/digest/weekly?week_of={week2_date.isoformat()}", headers=auth_header)

    # Get page 1 with per_page=1
    r = client.get("/digest/weekly/history?page=1&per_page=1", headers=auth_header)
    assert r.status_code == 200
    page1 = r.get_json()
    assert page1["page"] == 1
    assert page1["per_page"] == 1
    assert len(page1["digests"]) == 1
    assert page1["total"] >= 2

    # Get page 2
    r = client.get("/digest/weekly/history?page=2&per_page=1", headers=auth_header)
    assert r.status_code == 200
    page2 = r.get_json()
    assert len(page2["digests"]) == 1


def test_weekly_digest_history_requires_auth(client):
    """History endpoint requires authentication."""
    r = client.get("/digest/weekly/history")
    assert r.status_code == 401


def test_weekly_digest_updates_existing_record(client, auth_header):
    """Re-fetching a digest for the same week updates the persisted record."""
    today = date.today()
    monday = _monday_of(today)

    # First expense and digest
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 100,
                "description": "First expense",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200

    # Add another expense and re-fetch
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 200,
                "description": "Second expense",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200

    # History should show the updated total, not duplicate entries
    r = client.get("/digest/weekly/history", headers=auth_header)
    assert r.status_code == 200
    history = r.get_json()

    current_week_digests = [
        d
        for d in history["digests"]
        if d["week_start"] == monday.isoformat()
    ]
    assert len(current_week_digests) == 1
    assert current_week_digests[0]["total_expenses"] == 300.0


def test_weekly_digest_spending_increase_insight(client, auth_header):
    """Digest generates spending increase insight when expenses rise significantly."""
    today = date.today()
    this_monday = _monday_of(today)
    last_monday = this_monday - timedelta(days=7)

    # Previous week: small spending
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 100,
                "description": "Last week",
                "date": last_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    # Current week: much higher spending (200% increase)
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 300,
                "description": "This week",
                "date": this_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Should have an insight about spending increase
    insights_text = " ".join(payload["insights"])
    assert "increased" in insights_text.lower() or "spending" in insights_text.lower()


def test_weekly_digest_spending_decrease_insight(client, auth_header):
    """Digest generates positive insight when expenses decrease significantly."""
    today = date.today()
    this_monday = _monday_of(today)
    last_monday = this_monday - timedelta(days=7)

    # Previous week: high spending
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 1000,
                "description": "Last week high",
                "date": last_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    # Current week: much lower spending
    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 100,
                "description": "This week low",
                "date": this_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    insights_text = " ".join(payload["insights"])
    assert "decreased" in insights_text.lower() or "great" in insights_text.lower()
