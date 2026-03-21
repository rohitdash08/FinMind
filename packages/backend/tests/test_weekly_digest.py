from datetime import date, timedelta


def _create_expenses(client, auth_header, days_ago_amounts):
    for days_ago, amount, exp_type in days_ago_amounts:
        d = (date.today() - timedelta(days=days_ago)).isoformat()
        client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": f"Expense {amount}",
                "date": d,
                "expense_type": exp_type,
            },
            headers=auth_header,
        )


def test_weekly_digest_empty(client, auth_header):
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "period" in data
    assert "summary" in data
    assert "category_breakdown" in data
    assert "daily_spending" in data
    assert "insights" in data
    assert data["summary"]["total_expenses"] == 0
    assert data["summary"]["transaction_count"] == 0
    assert len(data["daily_spending"]) == 7


def test_weekly_digest_with_expenses(client, auth_header):
    _create_expenses(client, auth_header, [
        (0, 50, "EXPENSE"),
        (1, 30, "EXPENSE"),
        (2, 100, "INCOME"),
        (3, 20, "EXPENSE"),
    ])

    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["total_expenses"] == 100.0
    assert data["summary"]["total_income"] == 100.0
    assert data["summary"]["net_flow"] == 0.0
    assert data["summary"]["transaction_count"] == 4


def test_weekly_digest_wow_comparison(client, auth_header):
    # Previous week: spend 200
    _create_expenses(client, auth_header, [
        (10, 100, "EXPENSE"),
        (11, 100, "EXPENSE"),
    ])
    # Current week: spend 100
    _create_expenses(client, auth_header, [
        (0, 50, "EXPENSE"),
        (1, 50, "EXPENSE"),
    ])

    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # Current week: 100, prev week: 200 -> -50%
    assert data["summary"]["wow_change_pct"] == -50.0
    assert data["summary"]["trend"] == "down"


def test_weekly_digest_with_ref_date(client, auth_header):
    ref = (date.today() - timedelta(days=14)).isoformat()
    r = client.get(f"/insights/weekly-digest?date={ref}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["period"]["week_end"] == ref


def test_weekly_digest_insights_generated(client, auth_header):
    # Create expenses to trigger insights
    _create_expenses(client, auth_header, [
        (0, 500, "EXPENSE"),
        (0, 200, "INCOME"),
    ])

    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # Should have at least one insight
    assert len(data["insights"]) >= 1


def test_weekly_digest_category_breakdown(client, auth_header):
    # Create a category
    r = client.post(
        "/categories", json={"name": "Food"}, headers=auth_header
    )
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Create expense with category
    client.post(
        "/expenses",
        json={
            "amount": 75,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "category_id": cat_id,
        },
        headers=auth_header,
    )

    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["category_breakdown"]) >= 1
    assert data["category_breakdown"][0]["category_name"] == "Food"
    assert data["category_breakdown"][0]["share_pct"] == 100.0


def test_weekly_digest_daily_spending_all_days(client, auth_header):
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["daily_spending"]) == 7


def test_send_digest_email_endpoint(client, auth_header):
    r = client.post("/insights/weekly-digest/send", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "sent" in data
