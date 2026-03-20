"""Tests for Essential vs Discretionary Spending Breakdown (#120)."""
from __future__ import annotations

from datetime import date

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _add_expense(client, auth_header, amount: float, exp_date: str,
                 category_id: int | None = None, expense_type: str = "EXPENSE"):
    payload = {
        "amount": amount,
        "description": f"Test expense {amount}",
        "date": exp_date,
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _add_category(client, auth_header, name: str) -> int:
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def _get_breakdown(client, auth_header, month: str):
    return client.get(
        f"/insights/spending-breakdown?month={month}", headers=auth_header
    )


def _month_str(months_ago: int = 0) -> str:
    today = date.today()
    year, month = today.year, today.month
    for _ in range(months_ago):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return f"{year:04d}-{month:02d}"


def _first_day(ym: str) -> str:
    return f"{ym}-01"


# ── Endpoint tests ─────────────────────────────────────────────────────────────

class TestSpendingBreakdownEndpoint:

    def test_requires_authentication(self, client):
        """Without token, returns 401."""
        r = client.get("/insights/spending-breakdown?month=2025-01")
        assert r.status_code == 401

    def test_returns_200_for_authenticated_user(self, client, auth_header):
        """Authenticated request returns 200 with expected schema."""
        ym = _month_str(1)
        r = _get_breakdown(client, auth_header, ym)
        assert r.status_code == 200
        data = r.get_json()
        required = [
            "month", "total_spent", "essential_total", "discretionary_total",
            "uncategorized_total", "essential_percentage", "discretionary_percentage",
            "uncategorized_percentage", "categories", "insight",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_empty_month_returns_zero_totals(self, client, auth_header):
        """No expenses in month returns all zeros."""
        r = _get_breakdown(client, auth_header, "2020-01")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_spent"] == 0.0
        assert data["essential_total"] == 0.0
        assert data["discretionary_total"] == 0.0
        assert data["categories"] == []

    def test_defaults_to_current_month(self, client, auth_header):
        """Omitting month param returns current month."""
        r = client.get("/insights/spending-breakdown", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["month"] == date.today().strftime("%Y-%m")

    def test_month_echoed_in_response(self, client, auth_header):
        """Response month matches the queried month."""
        ym = _month_str(2)
        r = _get_breakdown(client, auth_header, ym)
        assert r.status_code == 200
        assert r.get_json()["month"] == ym


# ── Classification tests ───────────────────────────────────────────────────────

class TestCategoryClassification:

    def test_grocery_classified_as_essential(self, client, auth_header):
        """Category named 'Groceries' is classified as essential."""
        cat_id = _add_category(client, auth_header, "Groceries")
        ym = _month_str(1)
        _add_expense(client, auth_header, 500.0, _first_day(ym), category_id=cat_id)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        grocery_cats = [c for c in data["categories"] if c["category_name"] == "Groceries"]
        assert len(grocery_cats) == 1
        assert grocery_cats[0]["classification"] == "essential"

    def test_dining_classified_as_discretionary(self, client, auth_header):
        """Category named 'Dining Out' is classified as discretionary."""
        cat_id = _add_category(client, auth_header, "Dining Out")
        ym = _month_str(1)
        _add_expense(client, auth_header, 300.0, _first_day(ym), category_id=cat_id)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        dining_cats = [c for c in data["categories"] if c["category_name"] == "Dining Out"]
        assert len(dining_cats) == 1
        assert dining_cats[0]["classification"] == "discretionary"

    def test_unknown_category_classified_as_uncategorized(self, client, auth_header):
        """Unknown category names get 'uncategorized' classification."""
        cat_id = _add_category(client, auth_header, "Miscellaneous2099")
        ym = _month_str(1)
        _add_expense(client, auth_header, 200.0, _first_day(ym), category_id=cat_id)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        misc_cats = [c for c in data["categories"] if c["category_name"] == "Miscellaneous2099"]
        assert len(misc_cats) == 1
        assert misc_cats[0]["classification"] == "uncategorized"

    def test_rent_classified_as_essential(self, client, auth_header):
        """'Rent' category is essential."""
        cat_id = _add_category(client, auth_header, "Monthly Rent")
        ym = _month_str(1)
        _add_expense(client, auth_header, 15000.0, _first_day(ym), category_id=cat_id)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        rent_cats = [c for c in data["categories"] if c["category_name"] == "Monthly Rent"]
        assert len(rent_cats) == 1
        assert rent_cats[0]["classification"] == "essential"

    def test_entertainment_classified_as_discretionary(self, client, auth_header):
        """'Entertainment' category is discretionary."""
        cat_id = _add_category(client, auth_header, "Entertainment")
        ym = _month_str(1)
        _add_expense(client, auth_header, 800.0, _first_day(ym), category_id=cat_id)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        ent_cats = [c for c in data["categories"] if c["category_name"] == "Entertainment"]
        assert len(ent_cats) == 1
        assert ent_cats[0]["classification"] == "discretionary"


# ── Percentage calculation tests ───────────────────────────────────────────────

class TestPercentageCalculations:

    def test_percentages_sum_to_100(self, client, auth_header):
        """essential + discretionary + uncategorized percentages sum to ~100."""
        ym = _month_str(1)
        cat1 = _add_category(client, auth_header, "Groceries A")
        cat2 = _add_category(client, auth_header, "Dining A")
        cat3 = _add_category(client, auth_header, "WeirdCategory2099")
        _add_expense(client, auth_header, 300.0, _first_day(ym), category_id=cat1)
        _add_expense(client, auth_header, 200.0, _first_day(ym), category_id=cat2)
        _add_expense(client, auth_header, 100.0, _first_day(ym), category_id=cat3)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        total_pct = (
            data["essential_percentage"]
            + data["discretionary_percentage"]
            + data["uncategorized_percentage"]
        )
        assert abs(total_pct - 100.0) < 1.0, f"Percentages don't sum to 100: {total_pct}"

    def test_totals_sum_correctly(self, client, auth_header):
        """essential_total + discretionary_total + uncategorized_total = total_spent."""
        ym = _month_str(1)
        cat1 = _add_category(client, auth_header, "Rent B")
        cat2 = _add_category(client, auth_header, "Movies B")
        _add_expense(client, auth_header, 1000.0, _first_day(ym), category_id=cat1)
        _add_expense(client, auth_header, 400.0, _first_day(ym), category_id=cat2)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        computed = round(
            data["essential_total"] + data["discretionary_total"] + data["uncategorized_total"],
            2,
        )
        assert abs(computed - data["total_spent"]) < 0.01

    def test_category_percentage_of_total(self, client, auth_header):
        """Individual category percentage_of_total is correctly computed."""
        ym = _month_str(1)
        cat1 = _add_category(client, auth_header, "Food C")
        cat2 = _add_category(client, auth_header, "Shopping C")
        _add_expense(client, auth_header, 750.0, _first_day(ym), category_id=cat1)
        _add_expense(client, auth_header, 250.0, _first_day(ym), category_id=cat2)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        food_cat = next(c for c in data["categories"] if c["category_name"] == "Food C")
        assert abs(food_cat["percentage_of_total"] - 75.0) < 1.0

    def test_income_expenses_excluded(self, client, auth_header):
        """INCOME type expenses do not appear in the breakdown."""
        ym = _month_str(1)
        cat_id = _add_category(client, auth_header, "Salary D")
        _add_expense(client, auth_header, 50000.0, _first_day(ym),
                     category_id=cat_id, expense_type="INCOME")

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        salary_cats = [c for c in data["categories"] if c["category_name"] == "Salary D"]
        assert len(salary_cats) == 0


# ── Insight text tests ─────────────────────────────────────────────────────────

class TestInsightGeneration:

    def test_insight_present_in_response(self, client, auth_header):
        """Response always includes a non-empty insight string."""
        r = _get_breakdown(client, auth_header, "2020-01")
        assert r.status_code == 200
        assert "insight" in r.get_json()
        assert isinstance(r.get_json()["insight"], str)

    def test_high_essential_insight(self, client, auth_header):
        """Mostly-essential spending triggers appropriate insight."""
        ym = _month_str(1)
        cat_id = _add_category(client, auth_header, "Rent E")
        _add_expense(client, auth_header, 9000.0, _first_day(ym), category_id=cat_id)

        r = _get_breakdown(client, auth_header, ym)
        data = r.get_json()
        # Insight should mention essential or flexibility
        insight = data["insight"].lower()
        assert "essential" in insight or "flexible" in insight or "flexibility" in insight