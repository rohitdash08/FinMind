"""Tests for Dynamic Budget Suggestions (#73)."""
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


def _get_suggestions(client, auth_header, month: str):
    return client.get(
        f"/insights/budget-suggestions?month={month}", headers=auth_header
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

class TestBudgetSuggestionsEndpoint:

    def test_requires_authentication(self, client):
        """Without token, returns 401."""
        r = client.get("/insights/budget-suggestions")
        assert r.status_code == 401

    def test_returns_200_for_authenticated_user(self, client, auth_header):
        """Authenticated request returns 200 with expected schema."""
        r = _get_suggestions(client, auth_header, _month_str(0))
        assert r.status_code == 200
        data = r.get_json()
        assert "reference_months" in data
        assert "suggestions_count" in data
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert isinstance(data["reference_months"], list)

    def test_no_suggestions_without_enough_data(self, client, auth_header):
        """Returns empty suggestions when user has fewer than MIN_MONTHS of data."""
        # Add data for only 1 month (min is 3)
        cat_id = _add_category(client, auth_header, "GroceriesTest99")
        _add_expense(client, auth_header, 500.0, _first_day(_month_str(1)),
                     category_id=cat_id)

        r = _get_suggestions(client, auth_header, _month_str(0))
        assert r.status_code == 200
        data = r.get_json()
        # Category with only 1 month of data should NOT produce a suggestion
        cat_suggestions = [
            s for s in data["suggestions"] if s["category_name"] == "GroceriesTest99"
        ]
        assert len(cat_suggestions) == 0

    def test_defaults_to_current_month(self, client, auth_header):
        """Omitting month param uses current month as anchor."""
        r = client.get("/insights/budget-suggestions", headers=auth_header)
        assert r.status_code == 200

    def test_reference_months_has_six_entries(self, client, auth_header):
        """reference_months always contains exactly 6 entries (MAX_MONTHS)."""
        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        assert len(data["reference_months"]) == 6

    def test_reference_months_format(self, client, auth_header):
        """reference_months entries are YYYY-MM strings."""
        r = _get_suggestions(client, auth_header, _month_str(0))
        for ym in r.get_json()["reference_months"]:
            assert len(ym) == 7
            assert ym[4] == "-"
            assert ym[:4].isdigit()
            assert ym[5:].isdigit()


# ── Suggestion quality tests ───────────────────────────────────────────────────

class TestSuggestionQuality:

    def _seed_3_months(self, client, auth_header, cat_id: int, amounts: list[float]):
        """Seed 3 months of data (oldest to newest) for a category."""
        for i, amount in enumerate(amounts):
            ym = _month_str(3 - i)  # 3 months ago, 2 months ago, 1 month ago
            _add_expense(client, auth_header, amount, _first_day(ym),
                         category_id=cat_id)

    def test_generates_suggestion_with_3_months_data(self, client, auth_header):
        """Category with exactly 3 months of data produces a suggestion."""
        cat_id = _add_category(client, auth_header, "FoodGen3M")
        self._seed_3_months(client, auth_header, cat_id, [500.0, 480.0, 520.0])

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        cat_sug = [s for s in data["suggestions"] if s["category_name"] == "FoodGen3M"]
        assert len(cat_sug) == 1

    def test_suggestion_schema(self, client, auth_header):
        """Suggestion contains all required fields."""
        cat_id = _add_category(client, auth_header, "RentSchema")
        self._seed_3_months(client, auth_header, cat_id, [10000.0, 10000.0, 10000.0])

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        cat_sug = [s for s in data["suggestions"] if s["category_name"] == "RentSchema"]
        assert len(cat_sug) >= 1
        s = cat_sug[0]
        required = [
            "category_id", "category_name", "avg_monthly_spend",
            "stddev_monthly_spend", "suggested_budget", "confidence_score",
            "months_of_data", "rationale",
        ]
        for field in required:
            assert field in s, f"Missing field: {field}"

    def test_suggested_budget_above_average(self, client, auth_header):
        """Suggested budget is always >= average monthly spend (includes buffer)."""
        cat_id = _add_category(client, auth_header, "DiningBudget")
        self._seed_3_months(client, auth_header, cat_id, [300.0, 350.0, 320.0])

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        cat_sug = [s for s in data["suggestions"] if s["category_name"] == "DiningBudget"]
        assert len(cat_sug) >= 1
        s = cat_sug[0]
        assert s["suggested_budget"] >= s["avg_monthly_spend"]

    def test_confidence_score_range(self, client, auth_header):
        """Confidence score is always between 0 and 1."""
        cat_id = _add_category(client, auth_header, "ConfidenceTest")
        self._seed_3_months(client, auth_header, cat_id, [200.0, 210.0, 190.0])

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        for s in data["suggestions"]:
            assert 0.0 <= s["confidence_score"] <= 1.0, (
                f"Confidence out of range: {s['confidence_score']}"
            )

    def test_confidence_increases_with_more_months(self, client, auth_header):
        """3 months of data has lower confidence than 6 months."""
        # 3 months of data -> confidence = 3/6 = 0.5
        cat_id = _add_category(client, auth_header, "ConfLow3M")
        self._seed_3_months(client, auth_header, cat_id, [400.0, 420.0, 410.0])

        # 6 months of data -> confidence = 6/6 = 1.0
        cat_id2 = _add_category(client, auth_header, "ConfHigh6M")
        for i in range(1, 7):
            ym = _month_str(i)
            _add_expense(client, auth_header, 500.0, _first_day(ym), category_id=cat_id2)

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        low_conf = next((s for s in data["suggestions"] if s["category_name"] == "ConfLow3M"), None)
        high_conf = next((s for s in data["suggestions"] if s["category_name"] == "ConfHigh6M"), None)

        if low_conf and high_conf:
            assert low_conf["confidence_score"] < high_conf["confidence_score"]

    def test_rationale_is_non_empty_string(self, client, auth_header):
        """Every suggestion has a non-empty rationale string."""
        cat_id = _add_category(client, auth_header, "RationaleTest")
        self._seed_3_months(client, auth_header, cat_id, [500.0, 480.0, 510.0])

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        for s in data["suggestions"]:
            assert isinstance(s["rationale"], str)
            assert len(s["rationale"]) > 0

    def test_suggestions_sorted_by_avg_spend_desc(self, client, auth_header):
        """Suggestions are sorted highest avg_monthly_spend first."""
        cat_high = _add_category(client, auth_header, "HighSpend")
        cat_low = _add_category(client, auth_header, "LowSpend")
        self._seed_3_months(client, auth_header, cat_high, [2000.0, 1900.0, 2100.0])
        self._seed_3_months(client, auth_header, cat_low, [100.0, 110.0, 90.0])

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        avgs = [s["avg_monthly_spend"] for s in data["suggestions"]]
        # Should be in descending order
        assert avgs == sorted(avgs, reverse=True)

    def test_income_excluded_from_suggestions(self, client, auth_header):
        """INCOME type expenses do not generate budget suggestions."""
        cat_id = _add_category(client, auth_header, "SalaryIncome")
        for i in range(1, 4):
            ym = _month_str(i)
            _add_expense(client, auth_header, 50000.0, _first_day(ym),
                         category_id=cat_id, expense_type="INCOME")

        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        income_sug = [s for s in data["suggestions"] if s["category_name"] == "SalaryIncome"]
        assert len(income_sug) == 0

    def test_suggestions_count_matches_list_length(self, client, auth_header):
        """suggestions_count field equals len(suggestions)."""
        r = _get_suggestions(client, auth_header, _month_str(0))
        data = r.get_json()
        assert data["suggestions_count"] == len(data["suggestions"])