from datetime import date, timedelta


def test_dashboard_summary_returns_live_data(client, auth_header):
    # Create category for breakdown checks
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    # Seed one income and one expense
    r = client.post(
        "/expenses",
        json={
            "amount": 3000,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Seed bill
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": (date.today() + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert "summary" in payload
    assert payload["summary"]["monthly_income"] >= 3000
    assert payload["summary"]["monthly_expenses"] >= 500
    assert payload["summary"]["net_flow"] >= 2500

    assert isinstance(payload["recent_transactions"], list)
    assert any(t["description"] == "Salary" for t in payload["recent_transactions"])
    assert any(t["type"] == "INCOME" for t in payload["recent_transactions"])

    assert isinstance(payload["upcoming_bills"], list)
    assert len(payload["upcoming_bills"]) >= 1
    assert isinstance(payload["category_breakdown"], list)
    assert any(c["category_name"] == "Food" for c in payload["category_breakdown"])


def test_dashboard_summary_supports_month_filter(client, auth_header):
    month_a = date.today().replace(day=1)
    month_b = (month_a - timedelta(days=1)).replace(day=1)

    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Current Month Expense",
            "date": month_a.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 999,
            "description": "Previous Month Expense",
            "date": month_b.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/dashboard/summary?month={month_a.strftime('%Y-%m')}", headers=auth_header
    )
    assert r.status_code == 200
    data_a = r.get_json()
    assert data_a["period"]["month"] == month_a.strftime("%Y-%m")
    assert data_a["summary"]["monthly_expenses"] == 200.0

    r = client.get(
        f"/dashboard/summary?month={month_b.strftime('%Y-%m')}", headers=auth_header
    )
    assert r.status_code == 200
    data_b = r.get_json()
    assert data_b["period"]["month"] == month_b.strftime("%Y-%m")
    assert data_b["summary"]["monthly_expenses"] == 999.0


# ---------------------------------------------------------------------------
# Dashboard preferences tests
# ---------------------------------------------------------------------------

EXPECTED_WIDGET_IDS = {
    "summary_cards",
    "recent_transactions",
    "upcoming_bills",
    "category_breakdown",
}


def test_get_preferences_returns_defaults_for_new_user(client, auth_header):
    r = client.get("/dashboard/preferences", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert "widgets" in body
    widgets = body["widgets"]
    assert isinstance(widgets, list)
    assert len(widgets) == 4
    ids = {w["id"] for w in widgets}
    assert ids == EXPECTED_WIDGET_IDS
    # All visible by default
    assert all(w["visible"] is True for w in widgets)
    # First widget is summary_cards
    assert widgets[0]["id"] == "summary_cards"


def test_put_preferences_saves_and_returns_updated_config(client, auth_header):
    new_config = [
        {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True},
        {"id": "recent_transactions", "label": "Recent Transactions", "visible": False},
        {"id": "summary_cards", "label": "Summary Cards", "visible": True},
        {"id": "category_breakdown", "label": "Category Breakdown", "visible": False},
    ]
    r = client.put(
        "/dashboard/preferences",
        json={"widgets": new_config},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["widgets"][0]["id"] == "upcoming_bills"
    assert body["widgets"][1]["visible"] is False


def test_get_preferences_reflects_saved_order(client, auth_header):
    """After PUT the GET endpoint returns the persisted config."""
    new_config = [
        {"id": "category_breakdown", "label": "Category Breakdown", "visible": True},
        {"id": "summary_cards", "label": "Summary Cards", "visible": False},
        {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True},
        {"id": "recent_transactions", "label": "Recent Transactions", "visible": True},
    ]
    put_r = client.put(
        "/dashboard/preferences",
        json={"widgets": new_config},
        headers=auth_header,
    )
    assert put_r.status_code == 200

    get_r = client.get("/dashboard/preferences", headers=auth_header)
    assert get_r.status_code == 200
    widgets = get_r.get_json()["widgets"]
    assert widgets[0]["id"] == "category_breakdown"
    assert widgets[1]["visible"] is False


def test_put_preferences_rejects_unknown_widget_id(client, auth_header):
    bad_config = [
        {"id": "summary_cards", "label": "Summary Cards", "visible": True},
        {"id": "nonexistent_widget", "label": "Ghost", "visible": True},
    ]
    r = client.put(
        "/dashboard/preferences",
        json={"widgets": bad_config},
        headers=auth_header,
    )
    assert r.status_code == 422
    assert "nonexistent_widget" in r.get_json()["error"]


def test_put_preferences_rejects_duplicate_widget_id(client, auth_header):
    dup_config = [
        {"id": "summary_cards", "label": "Summary Cards", "visible": True},
        {"id": "summary_cards", "label": "Summary Cards", "visible": False},
        {"id": "recent_transactions", "label": "Recent Transactions", "visible": True},
        {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True},
    ]
    r = client.put(
        "/dashboard/preferences",
        json={"widgets": dup_config},
        headers=auth_header,
    )
    assert r.status_code == 422


def test_put_preferences_rejects_missing_widgets_field(client, auth_header):
    r = client.put(
        "/dashboard/preferences",
        json={"layout": []},
        headers=auth_header,
    )
    assert r.status_code == 422


def test_put_preferences_is_idempotent(client, auth_header):
    config = [
        {"id": "summary_cards", "label": "Summary Cards", "visible": True},
        {"id": "recent_transactions", "label": "Recent Transactions", "visible": True},
        {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": False},
        {"id": "category_breakdown", "label": "Category Breakdown", "visible": True},
    ]
    for _ in range(3):
        r = client.put(
            "/dashboard/preferences",
            json={"widgets": config},
            headers=auth_header,
        )
        assert r.status_code == 200

    r = client.get("/dashboard/preferences", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["widgets"][2]["id"] == "upcoming_bills"
    assert r.get_json()["widgets"][2]["visible"] is False


def test_preferences_are_isolated_per_user(client, app_fixture):
    """Two users each get their own independent dashboard config."""
    def make_auth_header(email, password):
        client.post("/auth/register", json={"email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    hdr_a = make_auth_header("alice@example.com", "passwordAlice1")
    hdr_b = make_auth_header("bob@example.com", "passwordBob1")

    config_a = [
        {"id": "category_breakdown", "label": "Category Breakdown", "visible": False},
        {"id": "summary_cards", "label": "Summary Cards", "visible": True},
        {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True},
        {"id": "recent_transactions", "label": "Recent Transactions", "visible": True},
    ]
    client.put("/dashboard/preferences", json={"widgets": config_a}, headers=hdr_a)

    # Bob still gets the default
    r_b = client.get("/dashboard/preferences", headers=hdr_b)
    assert r_b.get_json()["widgets"][0]["id"] == "summary_cards"
    assert r_b.get_json()["widgets"][0]["visible"] is True

    # Alice has her custom order
    r_a = client.get("/dashboard/preferences", headers=hdr_a)
    assert r_a.get_json()["widgets"][0]["id"] == "category_breakdown"
