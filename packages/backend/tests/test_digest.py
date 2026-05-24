"""Tests for the weekly digest service and routes."""
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_expense(client, auth_header, amount, days_ago=0, notes="test expense"):
    spent = (date.today() - timedelta(days=days_ago)).isoformat()
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": notes,
            "date": spent,
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

def test_digest_preview_empty(client, auth_header):
    """Preview with no expenses returns zero totals."""
    r = client.get("/digest/preview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 0.0
    assert data["num_transactions"] == 0
    assert data["top_categories"] == []
    assert data["largest_expense"] is None
    assert "date_range" in data
    assert "wow_change_pct" in data


def test_digest_preview_with_expenses(client, auth_header):
    """Preview aggregates this week's expenses correctly."""
    _add_expense(client, auth_header, 100, days_ago=1, notes="Grocery run")
    _add_expense(client, auth_header, 50, days_ago=2, notes="Bus pass")
    _add_expense(client, auth_header, 200, days_ago=3, notes="Monthly rent")

    r = client.get("/digest/preview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["total_spent"] == 350.0
    assert data["num_transactions"] == 3
    assert data["largest_expense"]["amount"] == 200.0
    assert data["largest_expense"]["notes"] == "Monthly rent"


def test_digest_preview_excludes_income(client, auth_header):
    """Income transactions must not be included in the digest totals."""
    _add_expense(client, auth_header, 500, days_ago=0, notes="Salary")
    r_income = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r_income.status_code == 201

    r = client.get("/digest/preview", headers=auth_header)
    data = r.get_json()
    # Only the EXPENSE record should be counted
    assert data["total_spent"] == 500.0
    assert data["num_transactions"] == 1


def test_digest_preview_excludes_old_expenses(client, auth_header):
    """Expenses older than 7 days must not appear in the current digest."""
    _add_expense(client, auth_header, 999, days_ago=8, notes="Old expense")
    _add_expense(client, auth_header, 50, days_ago=1, notes="Recent expense")

    r = client.get("/digest/preview", headers=auth_header)
    data = r.get_json()
    assert data["total_spent"] == 50.0
    assert data["num_transactions"] == 1


def test_digest_wow_change_zero_when_no_previous(client, auth_header):
    """Week-over-week change is 0 when there are no prior-week expenses."""
    _add_expense(client, auth_header, 100, days_ago=0)

    r = client.get("/digest/preview", headers=auth_header)
    data = r.get_json()
    assert data["wow_change_pct"] == 0.0


def test_digest_wow_change_calculated(client, auth_header):
    """Week-over-week change reflects spend vs the previous 7-day window."""
    # Previous week: spend 100
    _add_expense(client, auth_header, 100, days_ago=10, notes="Last week")
    # Current week: spend 150  → +50 %
    _add_expense(client, auth_header, 150, days_ago=2, notes="This week")

    r = client.get("/digest/preview", headers=auth_header)
    data = r.get_json()
    assert data["wow_change_pct"] == 50.0


def test_digest_top_categories_capped_at_three(client, auth_header):
    """top_categories contains at most 3 entries."""
    for i, amount in enumerate([10, 20, 30, 40, 50], start=1):
        _add_expense(client, auth_header, amount, days_ago=i % 6, notes=f"Item {i}")

    r = client.get("/digest/preview", headers=auth_header)
    data = r.get_json()
    assert len(data["top_categories"]) <= 3


# ---------------------------------------------------------------------------
# Send-test endpoint
# ---------------------------------------------------------------------------

def test_digest_send_test_no_smtp(client, auth_header):
    """send-test returns 202 when SMTP is not configured (test environment)."""
    r = client.post("/digest/send-test", headers=auth_header)
    # 200 = sent, 202 = built but SMTP not configured
    assert r.status_code in (200, 202)
    body = r.get_json()
    assert "email" in body
    assert "message" in body


def test_digest_send_test_requires_auth(client):
    """send-test must be protected by JWT."""
    r = client.post("/digest/send-test")
    assert r.status_code == 401


def test_digest_preview_requires_auth(client):
    """preview must be protected by JWT."""
    r = client.get("/digest/preview")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# HTML renderer (unit test — no DB needed)
# ---------------------------------------------------------------------------

def test_digest_html_render_basic():
    from app.services.digest import render_digest_html

    data = {
        "currency": "INR",
        "date_range": "2026-05-18 – 2026-05-24",
        "total_spent": 350.0,
        "wow_change_pct": 12.5,
        "num_transactions": 3,
        "top_categories": [
            {"name": "Food", "amount": 200.0},
            {"name": "Transport", "amount": 150.0},
        ],
        "largest_expense": {
            "amount": 200.0,
            "notes": "Restaurant dinner",
            "date": "2026-05-22",
        },
    }
    html = render_digest_html(data)
    assert "350.00" in html
    assert "Food" in html
    assert "+12.5%" in html
    assert "Restaurant dinner" in html
    assert "INR" in html


def test_digest_html_render_no_expenses():
    from app.services.digest import render_digest_html

    data = {
        "currency": "USD",
        "date_range": "2026-05-18 – 2026-05-24",
        "total_spent": 0.0,
        "wow_change_pct": 0.0,
        "num_transactions": 0,
        "top_categories": [],
        "largest_expense": None,
    }
    html = render_digest_html(data)
    assert "No expenses recorded this week" in html
    assert "0.00" in html


def test_digest_html_render_negative_wow():
    from app.services.digest import render_digest_html

    data = {
        "currency": "GBP",
        "date_range": "2026-05-18 – 2026-05-24",
        "total_spent": 80.0,
        "wow_change_pct": -20.0,
        "num_transactions": 2,
        "top_categories": [{"name": "Groceries", "amount": 80.0}],
        "largest_expense": {"amount": 80.0, "notes": "Supermarket", "date": "2026-05-20"},
    }
    html = render_digest_html(data)
    assert "-20.0%" in html
    assert "down" in html


# ---------------------------------------------------------------------------
# build_weekly_digest unit test
# ---------------------------------------------------------------------------

def test_build_weekly_digest_returns_required_keys(client, auth_header):
    r = client.get("/digest/preview", headers=auth_header)
    data = r.get_json()
    required = {
        "user_id", "currency", "date_range", "week_start", "week_end",
        "total_spent", "total_previous_week", "wow_change_pct",
        "num_transactions", "top_categories", "all_categories", "largest_expense",
    }
    assert required.issubset(data.keys()), f"Missing keys: {required - data.keys()}"
