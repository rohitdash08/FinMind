from datetime import date, timedelta


def _category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _expense(client, auth_header, amount, description, spent_at, **extra):
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at.isoformat(),
        **extra,
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_weekly_summary_returns_trends_categories_and_bills(client, auth_header):
    monday = date(2026, 5, 25)
    dining = _category(client, auth_header, "Dining")
    travel = _category(client, auth_header, "Travel")

    _expense(
        client,
        auth_header,
        800,
        "Salary",
        monday,
        expense_type="INCOME",
        currency="USD",
    )
    _expense(
        client,
        auth_header,
        120,
        "Team dinner",
        monday + timedelta(days=1),
        category_id=dining,
        currency="USD",
    )
    _expense(
        client,
        auth_header,
        80,
        "Train tickets",
        monday + timedelta(days=2),
        category_id=travel,
        currency="USD",
    )
    _expense(
        client,
        auth_header,
        50,
        "Previous week food",
        monday - timedelta(days=3),
        category_id=dining,
        currency="USD",
    )
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 40,
            "currency": "USD",
            "next_due_date": (monday + timedelta(days=4)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-summary?week_start={monday.isoformat()}&currency=USD",
        headers=auth_header,
    )

    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period"]["week_start"] == monday.isoformat()
    assert payload["summary"]["income"] == 800.0
    assert payload["summary"]["expenses"] == 200.0
    assert payload["summary"]["net_flow"] == 600.0
    assert payload["comparison"]["previous_expenses"] == 50.0
    assert payload["comparison"]["expense_delta"] == 150.0
    assert payload["comparison"]["expense_delta_pct"] == 300.0
    assert payload["category_breakdown"][0]["category_name"] == "Dining"
    assert payload["category_breakdown"][0]["amount"] == 120.0
    assert len(payload["daily_breakdown"]) == 7
    assert payload["top_expenses"][0]["description"] == "Team dinner"
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert payload["method"] == "deterministic"
    assert payload["insights"]
    assert payload["recommendations"]


def test_weekly_summary_normalizes_any_week_date_to_monday(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-28",
        headers=auth_header,
    )

    assert r.status_code == 200
    assert r.get_json()["period"]["week_start"] == "2026-05-25"


def test_weekly_summary_rejects_invalid_week_start(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=not-a-date", headers=auth_header
    )

    assert r.status_code == 400
    assert "invalid week_start" in r.get_json()["error"]
