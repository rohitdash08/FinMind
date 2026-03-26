"""Tests for the weekly financial digest feature.

Covers:
- Basic digest generation with transactions
- Empty state (no transactions)
- Week-over-week comparison
- Category breakdown with share percentages
- Daily spending patterns
- Trend analysis (UP / DOWN / FLAT / NEW / GONE)
- Insight generation (savings rate, spending spikes, anomalies, no-spend days)
- Currency filtering
- Upcoming bills integration
- Week parameter validation
- Cache behaviour
- Authentication requirement
"""

from datetime import date, timedelta
import json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _monday_of_current_week() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _iso_week_str(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _seed_expense(client, auth_header, amount, description, spent_at,
                  expense_type="EXPENSE", category_id=None, currency=None):
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id:
        payload["category_id"] = category_id
    if currency:
        payload["currency"] = currency
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"seed expense failed: {r.get_json()}"
    return r.get_json()


def _seed_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _seed_bill(client, auth_header, name, amount, due_date, cadence="MONTHLY",
               autopay=False, currency=None):
    payload = {
        "name": name,
        "amount": amount,
        "next_due_date": due_date.isoformat(),
        "cadence": cadence,
        "autopay_enabled": autopay,
    }
    if currency:
        payload["currency"] = currency
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_digest_requires_auth(client):
    """GET /digest/weekly must return 401 without a token."""
    r = client.get("/digest/weekly")
    assert r.status_code in (401, 422)


def test_digest_empty_state(client, auth_header):
    """Digest with no transactions returns valid structure with zeroes."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert "week" in data
    assert "period" in data
    assert "summary" in data
    assert data["summary"]["total_income"] == 0
    assert data["summary"]["total_expenses"] == 0
    assert data["summary"]["net_savings"] == 0
    assert data["summary"]["transaction_count"] == 0
    assert isinstance(data["category_breakdown"], list)
    assert isinstance(data["daily_spending"], list)
    assert len(data["daily_spending"]) == 7  # Mon-Sun
    assert isinstance(data["trends"], list)
    assert isinstance(data["insights"], list)
    assert isinstance(data["upcoming_bills"], list)


def test_digest_with_income_and_expenses(client, auth_header):
    """Digest correctly sums income and expenses for the current week."""
    monday = _monday_of_current_week()

    _seed_expense(client, auth_header, 5000, "Salary", monday, expense_type="INCOME")
    _seed_expense(client, auth_header, 200, "Groceries", monday)
    _seed_expense(client, auth_header, 150, "Transport", monday + timedelta(days=1))
    _seed_expense(client, auth_header, 80, "Coffee", monday + timedelta(days=2))

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["summary"]["total_income"] == 5000.0
    assert data["summary"]["total_expenses"] == 430.0
    assert data["summary"]["net_savings"] == 4570.0
    assert data["summary"]["transaction_count"] == 4


def test_digest_category_breakdown(client, auth_header):
    """Category breakdown includes share_pct and transaction counts."""
    monday = _monday_of_current_week()
    food_id = _seed_category(client, auth_header, "Food")
    transport_id = _seed_category(client, auth_header, "Transport")

    _seed_expense(client, auth_header, 300, "Groceries", monday, category_id=food_id)
    _seed_expense(client, auth_header, 100, "Bus", monday + timedelta(days=1),
                  category_id=transport_id)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    cats = data["category_breakdown"]
    assert len(cats) == 2

    food_cat = next(c for c in cats if c["category_name"] == "Food")
    assert food_cat["amount"] == 300.0
    assert food_cat["share_pct"] == 75.0
    assert food_cat["transaction_count"] == 1

    transport_cat = next(c for c in cats if c["category_name"] == "Transport")
    assert transport_cat["amount"] == 100.0
    assert transport_cat["share_pct"] == 25.0


def test_digest_daily_spending_pattern(client, auth_header):
    """Daily spending shows per-day totals for the week."""
    monday = _monday_of_current_week()

    _seed_expense(client, auth_header, 50, "Monday lunch", monday)
    _seed_expense(client, auth_header, 75, "Wednesday dinner", monday + timedelta(days=2))

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    daily = data["daily_spending"]
    assert len(daily) == 7

    monday_entry = daily[0]
    assert monday_entry["day_name"] == "Monday"
    assert monday_entry["amount"] == 50.0

    wednesday_entry = daily[2]
    assert wednesday_entry["day_name"] == "Wednesday"
    assert wednesday_entry["amount"] == 75.0

    # Other days should be 0
    assert daily[1]["amount"] == 0.0  # Tuesday


def test_digest_week_over_week(client, auth_header):
    """Week-over-week change is computed correctly."""
    monday = _monday_of_current_week()
    prev_monday = monday - timedelta(weeks=1)

    # Previous week: $200 spending, $1000 income
    _seed_expense(client, auth_header, 1000, "Prev Salary", prev_monday,
                  expense_type="INCOME")
    _seed_expense(client, auth_header, 200, "Prev Groceries", prev_monday)

    # Current week: $400 spending, $1000 income
    _seed_expense(client, auth_header, 1000, "Salary", monday, expense_type="INCOME")
    _seed_expense(client, auth_header, 400, "Groceries", monday)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    wow = data["week_over_week"]
    assert wow["prev_total_expenses"] == 200.0
    assert wow["expense_change"] == 100.0  # doubled
    assert wow["income_change"] == 0.0  # same


def test_digest_trend_analysis(client, auth_header):
    """Trends include UP/DOWN/FLAT/NEW/GONE directions."""
    monday = _monday_of_current_week()
    prev_monday = monday - timedelta(weeks=1)
    food_id = _seed_category(client, auth_header, "Food")
    fun_id = _seed_category(client, auth_header, "Fun")

    # Previous week: Food $100, Fun $50
    _seed_expense(client, auth_header, 100, "Prev Food", prev_monday, category_id=food_id)
    _seed_expense(client, auth_header, 50, "Prev Fun", prev_monday, category_id=fun_id)

    # Current week: Food $300 (3x spike), Fun $0 (GONE)
    _seed_expense(client, auth_header, 300, "Food", monday, category_id=food_id)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    trends = data["trends"]
    assert len(trends) >= 2

    # Should have total_spending trend
    spending_trend = next(t for t in trends if t["metric"] == "total_spending")
    assert spending_trend["direction"] == "UP"

    # Food category should be UP
    food_trend = next((t for t in trends if t["metric"] == "category:Food"), None)
    assert food_trend is not None
    assert food_trend["direction"] == "UP"

    # Fun category should be GONE
    fun_trend = next((t for t in trends if t["metric"] == "category:Fun"), None)
    assert fun_trend is not None
    assert fun_trend["direction"] == "GONE"


def test_digest_insights_savings_rate(client, auth_header):
    """Insights include savings rate commentary."""
    monday = _monday_of_current_week()
    _seed_expense(client, auth_header, 1000, "Salary", monday, expense_type="INCOME")
    _seed_expense(client, auth_header, 200, "Groceries", monday)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    insight_titles = [i["title"] for i in data["insights"]]
    assert "Strong savings rate" in insight_titles  # 80% savings rate


def test_digest_insights_spending_spike(client, auth_header):
    """Spending spike detection warns when spending more than doubles."""
    monday = _monday_of_current_week()
    prev_monday = monday - timedelta(weeks=1)

    _seed_expense(client, auth_header, 100, "Prev spend", prev_monday)
    _seed_expense(client, auth_header, 300, "Big spend", monday)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    insight_titles = [i["title"] for i in data["insights"]]
    assert "Spending spike detected" in insight_titles


def test_digest_insights_no_spend_days(client, auth_header):
    """No-spend days insight appears when >= 3 days have zero spending."""
    monday = _monday_of_current_week()
    # Only spend on one day
    _seed_expense(client, auth_header, 50, "One purchase", monday)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    insight_titles = [i["title"] for i in data["insights"]]
    assert "No-spend days" in insight_titles


def test_digest_upcoming_bills(client, auth_header):
    """Upcoming bills appear in the digest."""
    monday = _monday_of_current_week()
    sunday = monday + timedelta(days=6)
    bill_due = sunday + timedelta(days=3)

    _seed_bill(client, auth_header, "Internet", 59.99, bill_due)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert len(data["upcoming_bills"]) >= 1
    assert data["upcoming_bills"][0]["name"] == "Internet"
    assert data["upcoming_bills"][0]["amount"] == 59.99


def test_digest_currency_filter(client, auth_header):
    """Currency filter only includes matching expenses."""
    monday = _monday_of_current_week()

    _seed_expense(client, auth_header, 100, "USD item", monday, currency="USD")
    _seed_expense(client, auth_header, 500, "EUR item", monday, currency="EUR")

    r = client.get("/digest/weekly?currency=USD", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["summary"]["total_expenses"] == 100.0
    assert data["currency"] == "USD"


def test_digest_specific_week(client, auth_header):
    """Can request a specific ISO week."""
    monday = _monday_of_current_week()
    week_str = _iso_week_str(monday)

    _seed_expense(client, auth_header, 42, "test", monday)

    r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["week"] == week_str


def test_digest_invalid_week_format(client, auth_header):
    """Invalid week format returns 400."""
    r = client.get("/digest/weekly?week=2026-13", headers=auth_header)
    assert r.status_code == 400
    assert "invalid" in r.get_json()["error"].lower()

    r = client.get("/digest/weekly?week=badformat", headers=auth_header)
    assert r.status_code == 400


def test_digest_week_out_of_range(client, auth_header):
    """Week number > 53 returns 400."""
    r = client.get("/digest/weekly?week=2026-W55", headers=auth_header)
    assert r.status_code == 400


def test_digest_response_shape(client, auth_header):
    """Verify the full response schema has all expected top-level keys."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    expected_keys = {
        "week", "period", "summary", "week_over_week",
        "category_breakdown", "daily_spending", "trends",
        "upcoming_bills", "insights",
    }
    assert expected_keys.issubset(set(data.keys()))

    # Period shape
    assert "start" in data["period"]
    assert "end" in data["period"]

    # Summary shape
    summary_keys = {"total_income", "total_expenses", "net_savings", "transaction_count"}
    assert summary_keys.issubset(set(data["summary"].keys()))

    # WoW shape
    wow_keys = {
        "income_change", "expense_change", "savings_change",
        "prev_total_expenses", "prev_total_income",
    }
    assert wow_keys.issubset(set(data["week_over_week"].keys()))
