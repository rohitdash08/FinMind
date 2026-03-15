"""Tests for Predictive Financial Health Score (issue #90)."""

from datetime import date, timedelta


def _seed_expenses(client, auth_header, data, base_date=None):
    """Seed expense/income records. data = list of (amount, type, day_offset)."""
    for amount, etype, day_offset in data:
        d = (base_date or date.today()) - timedelta(days=day_offset)
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": f"Test {etype}",
                "date": d.isoformat(),
                "expense_type": etype,
            },
            headers=auth_header,
        )
        assert r.status_code == 201, f"Seed failed: {r.get_json()}"


def test_health_score_returns_structure(client, auth_header):
    """GET /health-score returns the expected response shape."""
    # Seed 3 months of data
    today = date.today()
    _seed_expenses(
        client,
        auth_header,
        [
            (5000, "INCOME", 5),
            (2000, "EXPENSE", 3),
            (5000, "INCOME", 35),
            (1800, "EXPENSE", 33),
            (5000, "INCOME", 65),
            (2200, "EXPENSE", 60),
        ],
        base_date=today,
    )

    r = client.get("/health-score", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Top-level keys
    assert "score" in payload
    assert "grade" in payload
    assert "breakdown" in payload
    assert "insights" in payload
    assert "months_analyzed" in payload

    # Score range
    assert 0 <= payload["score"] <= 100
    assert payload["grade"] in ("A+", "A", "B", "C", "D", "F", "N/A")

    # Breakdown has 4 components
    bd = payload["breakdown"]
    assert "savings_strength" in bd
    assert "spending_stability" in bd
    assert "bill_reliability" in bd
    assert "trend_direction" in bd

    # Each component has value and max
    for key in bd:
        assert 0 <= bd[key]["value"] <= bd[key]["max"]


def test_health_score_high_savings(client, auth_header):
    """High savings rate (50%+) should give strong savings score."""
    today = date.today()
    _seed_expenses(
        client,
        auth_header,
        [
            (10000, "INCOME", 5),
            (2000, "EXPENSE", 3),
            (10000, "INCOME", 35),
            (2500, "EXPENSE", 33),
            (10000, "INCOME", 65),
            (3000, "EXPENSE", 60),
        ],
        base_date=today,
    )

    r = client.get("/health-score", headers=auth_header)
    payload = r.get_json()

    savings_val = payload["breakdown"]["savings_strength"]["value"]
    assert savings_val >= 15, f"Expected high savings score, got {savings_val}"
    assert payload["score"] >= 50


def test_health_score_low_savings(client, auth_header):
    """Low savings rate (spending > income) should give low savings score."""
    today = date.today()
    _seed_expenses(
        client,
        auth_header,
        [
            (3000, "INCOME", 5),
            (4000, "EXPENSE", 3),
            (3000, "INCOME", 35),
            (3500, "EXPENSE", 33),
            (3000, "INCOME", 65),
            (4500, "EXPENSE", 60),
        ],
        base_date=today,
    )

    r = client.get("/health-score", headers=auth_header)
    payload = r.get_json()

    savings_val = payload["breakdown"]["savings_strength"]["value"]
    assert savings_val < 10, f"Expected low savings score, got {savings_val}"


def test_health_score_consistent_spending(client, auth_header):
    """Stable spending gives higher stability score."""
    today = date.today()
    expenses = []
    for i in range(6):
        expenses.extend([(5000, "INCOME", i * 30 + 5), (2000, "EXPENSE", i * 30 + 3)])

    _seed_expenses(client, auth_header, expenses, base_date=today)

    r = client.get("/health-score", headers=auth_header)
    payload = r.get_json()

    stability = payload["breakdown"]["spending_stability"]["value"]
    assert stability >= 18, f"Expected high stability for consistent spending, got {stability}"


def test_health_score_volatile_spending(client, auth_header):
    """Volatile spending gives lower stability score."""
    today = date.today()
    amounts = [500, 5000, 100, 3000, 200, 4000]
    data = []
    for i, amt in enumerate(amounts):
        data.extend([(8000, "INCOME", i * 30 + 5), (amt, "EXPENSE", i * 30 + 3)])

    _seed_expenses(client, auth_header, data, base_date=today)

    r = client.get("/health-score", headers=auth_header)
    payload = r.get_json()

    stability = payload["breakdown"]["spending_stability"]["value"]
    assert stability < 15, f"Expected low stability for volatile spending, got {stability}"


def test_health_score_insufficient_data(client, auth_header):
    """With 0 months of data, should return N/A grade."""
    r = client.get("/health-score", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["grade"] == "N/A"


def _first_of_month(year, month):
    """Return the first day of a given month."""
    from calendar import monthrange
    return date(year, month, 1)


def test_health_score_decreasing_expenses(client, auth_header):
    """Decreasing expenses over time should boost trend score."""
    # Seed expenses for 6 consecutive months with decreasing amounts.
    # i=0 is 6 months ago, i=5 is current month.
    from datetime import date, timedelta
    today = date.today()
    months_data = []
    for i in range(6):
        # Calculate month: i=0 → 6 months ago, i=5 → current month
        month = today.month - (5 - i)
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        d = date(year, month, 1)
        expense = 5000 - i * 500  # 5000, 4500, 4000, 3500, 3000, 2500 (decreasing)
        days_ago = (today - d).days
        months_data.extend([(6000, "INCOME", days_ago), (expense, "EXPENSE", days_ago)])

    _seed_expenses(client, auth_header, months_data, base_date=today)

    r = client.get("/health-score", headers=auth_header)
    payload = r.get_json()

    trend = payload["breakdown"]["trend_direction"]["value"]
    assert trend >= 15, f"Expected high trend score for decreasing expenses, got {trend}"


def test_health_score_increasing_expenses(client, auth_header):
    """Increasing expenses over time should lower trend score."""
    from datetime import date, timedelta
    today = date.today()
    months_data = []
    for i in range(6):
        month = today.month - (5 - i)
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        d = date(year, month, 1)
        expense = 2000 + i * 500  # 2000, 2500, 3000, 3500, 4000, 4500 (increasing)
        days_ago = (today - d).days
        months_data.extend([(6000, "INCOME", days_ago), (expense, "EXPENSE", days_ago)])

    _seed_expenses(client, auth_header, months_data, base_date=today)

    r = client.get("/health-score", headers=auth_header)
    payload = r.get_json()

    trend = payload["breakdown"]["trend_direction"]["value"]
    assert trend < 15, f"Expected low trend score for increasing expenses, got {trend}"
