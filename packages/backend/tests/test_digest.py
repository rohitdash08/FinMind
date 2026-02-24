"""
Tests for GET /digest/weekly

Covers:
  - Empty digest (no expenses → zeroes, no crash)
  - Single-week data (current only, no prior)
  - Full two-week comparison (spend delta, category trends, insights)
  - Category breakdown: share percentages sum to ~100
  - INCOME entries are excluded from spend totals
  - Trend directions: UP, DOWN, FLAT, NEW, GONE
  - Cache: second call is served from cache (same payload)
  - Auth: 401 without token
  - Multi-currency filter: EUR expenses excluded from INR digest (and vice versa)
  - Currency symbol display: insights use '₹'/'€'/'$', not raw ISO codes
  - Zero-in-target-currency: only foreign expenses → zero totals, no crash
"""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_expense(client, auth_header, amount, description, spent_at,
                  category_id=None, expense_type="EXPENSE"):
    return client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": description,
            "date": spent_at,
            "expense_type": expense_type,
            "category_id": category_id,
        },
        headers=auth_header,
    )


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    cats = r.get_json()
    return next(c["id"] for c in cats if c["name"] == name)


def _today_minus(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_weekly_digest_requires_auth(client):
    r = client.get("/digest/weekly")
    assert r.status_code == 401


def test_weekly_digest_empty(client, auth_header):
    """No expenses — endpoint should return valid structure with zero totals."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["current_week"]["total_spend"] == 0.0
    assert data["current_week"]["total_income"] == 0.0
    assert data["current_week"]["net_flow"] == 0.0
    assert data["prior_week"]["total_spend"] == 0.0
    assert data["category_trends"] == []
    assert data["top_categories"] == []
    assert isinstance(data["insights"], list)


def test_weekly_digest_current_week_only(client, auth_header):
    """Expenses only in current week — prior week is zero, trend directions are NEW."""
    food_id = _create_category(client, auth_header, "Food")

    _post_expense(client, auth_header, 200.00, "Lunch",    _today_minus(1), food_id)
    _post_expense(client, auth_header, 150.00, "Dinner",   _today_minus(2), food_id)
    _post_expense(client, auth_header, 300.00, "Groceries",_today_minus(3), food_id)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["current_week"]["total_spend"] == 650.0
    assert data["prior_week"]["total_spend"] == 0.0
    assert data["total_spend_delta"] == 650.0
    assert data["total_spend_pct_change"] is None  # no prior data

    food_trend = next(
        t for t in data["category_trends"] if t["category_name"] == "Food"
    )
    assert food_trend["direction"] == "NEW"
    assert food_trend["current_amount"] == 650.0
    assert food_trend["prior_amount"] == 0.0


def test_weekly_digest_income_excluded_from_spend(client, auth_header):
    """INCOME entries must not inflate total_spend."""
    _post_expense(client, auth_header, 5000.00, "Salary", _today_minus(2),
                  expense_type="INCOME")
    _post_expense(client, auth_header, 200.00, "Coffee",  _today_minus(1))

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["current_week"]["total_spend"] == 200.0
    assert data["current_week"]["total_income"] == 5000.0
    assert data["current_week"]["net_flow"] == 4800.0


def test_weekly_digest_week_over_week_comparison(client, auth_header):
    """Full two-week dataset: verify deltas, category trends, and insights."""
    food_id     = _create_category(client, auth_header, "Food")
    travel_id   = _create_category(client, auth_header, "Travel")
    health_id   = _create_category(client, auth_header, "Healthcare")

    # Current week (days 0-6)
    _post_expense(client, auth_header, 500.00, "Groceries",   _today_minus(1), food_id)
    _post_expense(client, auth_header, 300.00, "Restaurants",  _today_minus(3), food_id)
    _post_expense(client, auth_header, 800.00, "Flight",       _today_minus(2), travel_id)
    # income
    _post_expense(client, auth_header, 3000.00, "Freelance",   _today_minus(4),
                  expense_type="INCOME")

    # Prior week (days 7-13)
    _post_expense(client, auth_header, 400.00, "Groceries",   _today_minus(8),  food_id)
    _post_expense(client, auth_header, 600.00, "Hospital",    _today_minus(10), health_id)
    # Healthcare present in prior, absent in current → GONE

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    # Totals
    assert data["current_week"]["total_spend"] == 1600.0
    assert data["prior_week"]["total_spend"] == 1000.0
    assert data["total_spend_delta"] == 600.0
    assert data["total_spend_pct_change"] == 60.0

    # Income / net flow
    assert data["current_week"]["total_income"] == 3000.0
    assert data["current_week"]["net_flow"] == 1400.0

    # Category trends
    trends_by_name = {t["category_name"]: t for t in data["category_trends"]}

    # Food: present in both — UP (800 vs 400)
    assert trends_by_name["Food"]["direction"] == "UP"
    assert trends_by_name["Food"]["current_amount"] == 800.0
    assert trends_by_name["Food"]["prior_amount"] == 400.0
    assert trends_by_name["Food"]["delta"] == 400.0

    # Travel: only in current → NEW
    assert trends_by_name["Travel"]["direction"] == "NEW"
    assert trends_by_name["Travel"]["current_amount"] == 800.0

    # Healthcare: only in prior → GONE
    assert trends_by_name["Healthcare"]["direction"] == "GONE"
    assert trends_by_name["Healthcare"]["prior_amount"] == 600.0
    assert trends_by_name["Healthcare"]["current_amount"] == 0.0

    # Category share percentages for current week should sum to ~100
    current_cats = data["current_week"]["categories"]
    total_share = sum(c["share_pct"] for c in current_cats)
    assert abs(total_share - 100.0) < 0.1

    # Top categories should have at most 3 entries
    assert len(data["top_categories"]) <= 3

    # Insights are non-empty strings
    assert len(data["insights"]) > 0
    assert all(isinstance(s, str) and len(s) > 0 for s in data["insights"])


def test_weekly_digest_flat_category(client, auth_header):
    """Identical spend in both weeks for a category → direction FLAT."""
    food_id = _create_category(client, auth_header, "Food")

    _post_expense(client, auth_header, 250.00, "Lunch", _today_minus(2), food_id)
    _post_expense(client, auth_header, 250.00, "Lunch", _today_minus(9), food_id)

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    food_trend = next(
        t for t in data["category_trends"] if t["category_name"] == "Food"
    )
    assert food_trend["direction"] == "FLAT"
    assert food_trend["delta"] == 0.0
    assert food_trend["pct_change"] == 0.0


def test_weekly_digest_response_shape(client, auth_header):
    """All expected top-level keys are present in the response."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    required_keys = {
        "generated_at", "user_id", "currency",
        "current_week", "prior_week",
        "total_spend_delta", "total_spend_pct_change",
        "top_categories", "category_trends", "insights",
    }
    assert required_keys.issubset(data.keys())

    for week_key in ("current_week", "prior_week"):
        week = data[week_key]
        assert {"week_start", "week_end", "total_spend",
                "total_income", "net_flow", "categories"}.issubset(week.keys())


def test_weekly_digest_cached(client, auth_header):
    """Second call should return the same payload (served from cache)."""
    r1 = client.get("/digest/weekly", headers=auth_header)
    r2 = client.get("/digest/weekly", headers=auth_header)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.get_json() == r2.get_json()


# ---------------------------------------------------------------------------
# Currency filter + symbol tests
# Regression suite for:
#   - _load_expenses() currency= filter (prevents silent multi-currency
#     cross-contamination in totals)
#   - _currency_symbol() lookup (ensures insights use '₹' not 'INR' etc.)
# ---------------------------------------------------------------------------

def _post_expense_currency(client, auth_header, amount, description,
                           spent_at, currency, category_id=None,
                           expense_type="EXPENSE"):
    """Variant of _post_expense that includes the currency field."""
    return client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": description,
            "date": spent_at,
            "expense_type": expense_type,
            "category_id": category_id,
            "currency": currency,
        },
        headers=auth_header,
    )


def test_weekly_digest_multi_currency_filter_default(client, auth_header):
    """
    Mixed-currency expenses must NOT be summed together.

    Setup: 500 INR + 200 EUR in the current window.
    The default INR digest must return total_spend == 500.0, not 700.0.

    Catches the pre-fix bug where _load_expenses() fetched all currencies
    and _summarise_window() silently added 200 EUR into the INR total.
    """
    food_id = _create_category(client, auth_header, "Food")

    # INR expense — must appear in the default (INR) digest
    r = _post_expense_currency(
        client, auth_header, 500.00, "Groceries INR",
        _today_minus(2), "INR", food_id,
    )
    assert r.status_code == 201

    # EUR expense — must be excluded from the INR digest entirely
    r = _post_expense_currency(
        client, auth_header, 200.00, "Groceries EUR",
        _today_minus(2), "EUR", food_id,
    )
    assert r.status_code == 201

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["currency"] == "INR"
    assert data["current_week"]["total_spend"] == 500.0, (
        f"EUR expense leaked into INR digest — total_spend should be 500.0, "
        f"got {data['current_week']['total_spend']}"
    )
    # Categories should only reflect the INR expense
    assert len(data["current_week"]["categories"]) == 1
    assert data["current_week"]["categories"][0]["amount"] == 500.0


def test_weekly_digest_multi_currency_filter_explicit(client, auth_header):
    """
    Requesting digest with ?currency=EUR must only aggregate EUR expenses.

    Setup: 500 INR + 200 EUR.
    EUR digest must return total_spend == 200.0.
    """
    food_id = _create_category(client, auth_header, "Food")

    _post_expense_currency(
        client, auth_header, 500.00, "Groceries INR",
        _today_minus(2), "INR", food_id,
    )
    _post_expense_currency(
        client, auth_header, 200.00, "Groceries EUR",
        _today_minus(2), "EUR", food_id,
    )

    r = client.get("/digest/weekly?currency=EUR", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["currency"] == "EUR"
    assert data["current_week"]["total_spend"] == 200.0, (
        f"INR expense leaked into EUR digest — total_spend should be 200.0, "
        f"got {data['current_week']['total_spend']}"
    )


def test_weekly_digest_zero_in_target_currency(client, auth_header):
    """
    User has expenses in EUR only. Default INR digest must return zero
    totals — not crash, not leak the EUR amounts.

    Validates that the currency filter gracefully handles the case where
    no expenses exist in the requested currency.
    """
    _post_expense_currency(
        client, auth_header, 999.00, "Foreign spend",
        _today_minus(2), "EUR",
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["current_week"]["total_spend"] == 0.0
    assert data["current_week"]["total_income"] == 0.0
    assert data["current_week"]["categories"] == []
    assert data["category_trends"] == []
    assert isinstance(data["insights"], list)   # insights list still present


def test_weekly_digest_currency_symbol_in_insights(client, auth_header):
    """
    Insights must display the Unicode symbol ('₹', '€', '$'), NOT the raw
    ISO 4217 code ('INR', 'EUR', 'USD').

    Regression guard for: sym = currency → sym = _currency_symbol(currency).

    Uses INR (the default) because its symbol '₹' is unambiguously distinct
    from the code and cannot appear by coincidence.
    """
    _post_expense_currency(
        client, auth_header, 300.00, "Coffee",
        _today_minus(2), "INR",
    )

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    insights_text = " ".join(data["insights"])

    assert "₹" in insights_text, (
        f"Expected rupee symbol '₹' in insights but it was absent. "
        f"Insights: {insights_text!r}"
    )
    # 'INR ' (code followed by a space then a number) must not appear
    assert "INR " not in insights_text, (
        f"Raw ISO code 'INR' found in insights — _currency_symbol() lookup "
        f"is not being applied. Insights: {insights_text!r}"
    )
