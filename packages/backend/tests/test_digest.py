"""Tests for the weekly financial digest feature."""

from datetime import date, timedelta


def _last_monday():
    """Return the Monday of last completed week."""
    today = date.today()
    return today - timedelta(days=today.weekday() + 7)


def _seed_week(client, auth_header, week_start, expenses=None, incomes=None):
    """Helper: create expenses/incomes within a given week."""
    for i, (amount, desc) in enumerate(expenses or []):
        day = week_start + timedelta(days=min(i, 6))
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": desc,
                "date": day.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    for i, (amount, desc) in enumerate(incomes or []):
        day = week_start + timedelta(days=min(i, 6))
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": desc,
                "date": day.isoformat(),
                "expense_type": "INCOME",
            },
            headers=auth_header,
        )
        assert r.status_code == 201


class TestWeeklyDigestEndpoint:
    """Tests for GET /digest"""

    def test_digest_returns_complete_payload(self, client, auth_header):
        monday = _last_monday()
        _seed_week(
            client,
            auth_header,
            monday,
            expenses=[(100, "Groceries"), (50, "Coffee"), (200, "Electronics")],
            incomes=[(3000, "Salary")],
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        assert r.status_code == 200
        payload = r.get_json()

        # Structure checks
        assert "period" in payload
        assert payload["period"]["week_start"] == monday.isoformat()
        assert payload["period"]["week_end"] == (monday + timedelta(days=6)).isoformat()

        assert "summary" in payload
        assert payload["summary"]["total_income"] == 3000.0
        assert payload["summary"]["total_expenses"] == 350.0
        assert payload["summary"]["net_flow"] == 2650.0
        assert payload["summary"]["transaction_count"] == 4

        assert "comparison" in payload
        assert "week_over_week_change_pct" in payload["comparison"]

        assert "category_breakdown" in payload
        assert isinstance(payload["category_breakdown"], list)

        assert "daily_spending" in payload
        assert len(payload["daily_spending"]) == 7  # Always 7 days

        assert "top_transactions" in payload
        assert len(payload["top_transactions"]) <= 5

        assert "insights" in payload
        assert isinstance(payload["insights"], list)
        assert len(payload["insights"]) > 0

    def test_digest_defaults_to_last_week(self, client, auth_header):
        monday = _last_monday()
        _seed_week(
            client,
            auth_header,
            monday,
            expenses=[(75, "Lunch")],
        )

        r = client.get("/digest", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["period"]["week_start"] == monday.isoformat()

    def test_digest_empty_week(self, client, auth_header):
        # Use a far-past week with no data
        r = client.get("/digest?week_start=2020-01-06", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["summary"]["total_expenses"] == 0.0
        assert payload["summary"]["total_income"] == 0.0
        assert len(payload["daily_spending"]) == 7

    def test_digest_week_over_week_comparison(self, client, auth_header):
        monday = _last_monday()
        prev_monday = monday - timedelta(days=7)

        _seed_week(
            client, auth_header, prev_monday, expenses=[(200, "Prev week spend")]
        )
        _seed_week(
            client, auth_header, monday, expenses=[(300, "Current week spend")]
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        assert r.status_code == 200
        payload = r.get_json()

        assert payload["comparison"]["prev_week_expenses"] == 200.0
        assert payload["comparison"]["week_over_week_change_pct"] == 50.0

    def test_digest_top_transactions_ordered_by_amount(self, client, auth_header):
        monday = _last_monday()
        _seed_week(
            client,
            auth_header,
            monday,
            expenses=[(10, "Small"), (500, "Large"), (100, "Medium")],
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        assert r.status_code == 200
        top = r.get_json()["top_transactions"]
        amounts = [t["amount"] for t in top]
        assert amounts == sorted(amounts, reverse=True)

    def test_digest_daily_spending_has_seven_days(self, client, auth_header):
        monday = _last_monday()
        # Only one expense on Wednesday
        wed = monday + timedelta(days=2)
        client.post(
            "/expenses",
            json={
                "amount": 42,
                "description": "Wed only",
                "date": wed.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        assert r.status_code == 200
        daily = r.get_json()["daily_spending"]
        assert len(daily) == 7
        # Wednesday should have the spend
        wed_entry = next(d for d in daily if d["date"] == wed.isoformat())
        assert wed_entry["amount"] == 42.0
        # Other days should be 0
        zero_days = [d for d in daily if d["date"] != wed.isoformat()]
        assert all(d["amount"] == 0.0 for d in zero_days)

    def test_digest_with_categories(self, client, auth_header):
        monday = _last_monday()
        # Create a category
        r = client.post(
            "/categories", json={"name": "Food"}, headers=auth_header
        )
        assert r.status_code == 201
        food_id = r.get_json()["id"]

        client.post(
            "/expenses",
            json={
                "amount": 150,
                "description": "Groceries",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
                "category_id": food_id,
            },
            headers=auth_header,
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        assert r.status_code == 200
        cats = r.get_json()["category_breakdown"]
        assert len(cats) >= 1
        food_cat = next(c for c in cats if c["category_name"] == "Food")
        assert food_cat["amount"] == 150.0
        assert food_cat["share_pct"] == 100.0

    def test_digest_requires_auth(self, client):
        r = client.get("/digest")
        assert r.status_code == 401


class TestAvailableWeeksEndpoint:
    """Tests for GET /digest/weeks"""

    def test_weeks_returns_list(self, client, auth_header):
        monday = _last_monday()
        _seed_week(
            client, auth_header, monday, expenses=[(50, "Something")]
        )

        r = client.get("/digest/weeks", headers=auth_header)
        assert r.status_code == 200
        weeks = r.get_json()
        assert isinstance(weeks, list)
        assert len(weeks) >= 1
        assert weeks[0]["week_start"] == monday.isoformat()

    def test_weeks_empty_when_no_data(self, client, auth_header):
        r = client.get("/digest/weeks", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_weeks_count_param(self, client, auth_header):
        r = client.get("/digest/weeks?count=3", headers=auth_header)
        assert r.status_code == 200

    def test_weeks_requires_auth(self, client):
        r = client.get("/digest/weeks")
        assert r.status_code == 401


class TestDigestInsights:
    """Tests for insight generation logic."""

    def test_insights_include_spending_change(self, client, auth_header):
        monday = _last_monday()
        prev_monday = monday - timedelta(days=7)

        _seed_week(client, auth_header, prev_monday, expenses=[(100, "Prev")])
        _seed_week(client, auth_header, monday, expenses=[(150, "Curr")])

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        insights = r.get_json()["insights"]
        assert any("50.0%" in i for i in insights)

    def test_insights_include_savings(self, client, auth_header):
        monday = _last_monday()
        _seed_week(
            client,
            auth_header,
            monday,
            expenses=[(100, "Spend")],
            incomes=[(500, "Pay")],
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        insights = r.get_json()["insights"]
        assert any("saved" in i.lower() for i in insights)

    def test_insights_include_top_category(self, client, auth_header):
        monday = _last_monday()
        r = client.post(
            "/categories", json={"name": "Transport"}, headers=auth_header
        )
        cat_id = r.get_json()["id"]

        client.post(
            "/expenses",
            json={
                "amount": 200,
                "description": "Uber",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
                "category_id": cat_id,
            },
            headers=auth_header,
        )

        r = client.get(
            f"/digest?week_start={monday.isoformat()}", headers=auth_header
        )
        insights = r.get_json()["insights"]
        assert any("Transport" in i for i in insights)
