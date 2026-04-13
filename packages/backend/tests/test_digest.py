"""Tests for the weekly digest endpoint.

Covers:
  - Unauthenticated access
  - Empty state (no expenses)
  - Correct aggregation of income vs expenses
  - Category breakdown with percentage shares
  - Week-over-week comparison
  - Trend detection / insights generation
  - Invalid week format handling
  - Default week (current week)
"""

from datetime import date, timedelta


def _create_category(client, auth_header, name="Food"):
    resp = client.post(
        "/categories", json={"name": name}, headers=auth_header
    )
    assert resp.status_code in (200, 201)
    return resp.get_json()["id"]


def _create_expense(client, auth_header, amount, spent_at, notes="test",
                    expense_type="EXPENSE", category_id=None):
    payload = {
        "amount": amount,
        "date": spent_at,
        "description": notes,
        "expense_type": expense_type,
    }
    if category_id:
        payload["category_id"] = category_id
    resp = client.post("/expenses", json=payload, headers=auth_header)
    assert resp.status_code in (200, 201), f"Failed: {resp.get_json()}"
    return resp.get_json()


def _iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _monday_of_week(week_str: str) -> date:
    parts = week_str.split("-W")
    return date.fromisocalendar(int(parts[0]), int(parts[1]), 1)


class TestDigestAuth:
    """Test authentication requirements."""

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/digest/weekly")
        assert resp.status_code in (401, 422)


class TestDigestEmpty:
    """Test behavior with no expenses."""

    def test_empty_state(self, client, auth_header):
        resp = client.get("/digest/weekly", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["summary"]["total_expenses"] == 0
        assert data["summary"]["total_income"] == 0
        assert data["summary"]["net_flow"] == 0
        assert data["category_breakdown"] == []


class TestDigestAggregation:
    """Test correct aggregation of expenses and income."""

    def test_basic_aggregation(self, client, auth_header):
        today = date.today()
        week_str = _iso_week(today)
        monday = _monday_of_week(week_str)

        _create_expense(client, auth_header, 100, monday.isoformat(),
                        "Groceries")
        _create_expense(client, auth_header, 50, (monday + timedelta(days=1)).isoformat(),
                        "Coffee")
        _create_expense(client, auth_header, 500,
                        (monday + timedelta(days=2)).isoformat(),
                        "Salary", expense_type="INCOME")

        resp = client.get(f"/digest/weekly?week={week_str}",
                          headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["summary"]["total_expenses"] == 150.0
        assert data["summary"]["total_income"] == 500.0
        assert data["summary"]["net_flow"] == 350.0
        assert data["summary"]["transaction_count"] == 3

    def test_category_breakdown(self, client, auth_header):
        today = date.today()
        week_str = _iso_week(today)
        monday = _monday_of_week(week_str)

        food_id = _create_category(client, auth_header, "Food")
        transport_id = _create_category(client, auth_header, "Transport")

        _create_expense(client, auth_header, 80, monday.isoformat(),
                        "Lunch", category_id=food_id)
        _create_expense(client, auth_header, 20, monday.isoformat(),
                        "Bus", category_id=transport_id)

        resp = client.get(f"/digest/weekly?week={week_str}",
                          headers=auth_header)
        data = resp.get_json()

        assert len(data["category_breakdown"]) == 2
        food_entry = next(
            c for c in data["category_breakdown"]
            if c["category_id"] == food_id
        )
        assert food_entry["amount"] == 80.0
        assert food_entry["share_pct"] == 80.0
        assert food_entry["category_name"] == "Food"


class TestDigestWoW:
    """Test week-over-week comparison."""

    def test_wow_comparison(self, client, auth_header):
        today = date.today()
        week_str = _iso_week(today)
        monday = _monday_of_week(week_str)
        prev_monday = monday - timedelta(days=7)

        # Previous week: $100
        _create_expense(client, auth_header, 100,
                        prev_monday.isoformat(), "Last week lunch")

        # Current week: $200
        _create_expense(client, auth_header, 200,
                        monday.isoformat(), "This week lunch")

        resp = client.get(f"/digest/weekly?week={week_str}",
                          headers=auth_header)
        data = resp.get_json()

        wow = data["week_over_week"]
        assert wow["expense_delta"] == 100.0
        assert wow["expense_pct_change"] == 100.0
        assert wow["previous_week_expenses"] == 100.0


class TestDigestInsights:
    """Test automated insight generation."""

    def test_spending_spike_insight(self, client, auth_header):
        today = date.today()
        week_str = _iso_week(today)
        monday = _monday_of_week(week_str)
        prev_monday = monday - timedelta(days=7)

        # Previous week: $50
        _create_expense(client, auth_header, 50,
                        prev_monday.isoformat(), "Small purchase")

        # Current week: $200 (300% increase)
        _create_expense(client, auth_header, 200,
                        monday.isoformat(), "Big purchase")

        resp = client.get(f"/digest/weekly?week={week_str}",
                          headers=auth_header)
        data = resp.get_json()

        insight_types = [i["type"] for i in data["insights"]]
        insight_titles = [i["title"] for i in data["insights"]]
        assert "warning" in insight_types
        assert "Spending Spike" in insight_titles

    def test_savings_insight(self, client, auth_header):
        today = date.today()
        week_str = _iso_week(today)
        monday = _monday_of_week(week_str)
        prev_monday = monday - timedelta(days=7)

        # Previous week: $500
        _create_expense(client, auth_header, 500,
                        prev_monday.isoformat(), "Big week")

        # Current week: $50 (90% decrease)
        _create_expense(client, auth_header, 50,
                        monday.isoformat(), "Small week")

        resp = client.get(f"/digest/weekly?week={week_str}",
                          headers=auth_header)
        data = resp.get_json()

        insight_titles = [i["title"] for i in data["insights"]]
        assert "Great Savings" in insight_titles


class TestDigestValidation:
    """Test input validation."""

    def test_invalid_week_format(self, client, auth_header):
        resp = client.get("/digest/weekly?week=foobar",
                          headers=auth_header)
        assert resp.status_code == 400

    def test_invalid_week_number(self, client, auth_header):
        resp = client.get("/digest/weekly?week=2026-W99",
                          headers=auth_header)
        assert resp.status_code == 400

    def test_default_week(self, client, auth_header):
        resp = client.get("/digest/weekly", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "week" in data
        assert data["week"] == _iso_week(date.today())


class TestDigestDailyBreakdown:
    """Test daily spending breakdown."""

    def test_daily_array_has_7_days(self, client, auth_header):
        resp = client.get("/digest/weekly", headers=auth_header)
        data = resp.get_json()
        assert len(data["daily_spending"]) == 7
        assert data["daily_spending"][0]["day_name"] == "Monday"
        assert data["daily_spending"][6]["day_name"] == "Sunday"


class TestDigestTrends:
    """Test trend direction indicators."""

    def test_stable_trend_no_data(self, client, auth_header):
        resp = client.get("/digest/weekly", headers=auth_header)
        data = resp.get_json()
        assert data["trends"]["spending_direction"] in (
            "up", "down", "stable"
        )
        assert data["trends"]["income_direction"] in (
            "up", "down", "stable"
        )
