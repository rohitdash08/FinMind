"""Tests for the weekly financial digest feature."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────


def _monday_of_current_week():
    today = date.today()
    return today - timedelta(days=today.weekday())


def _create_expense(client, auth_header, *, amount, spent_date, notes="Test", expense_type="EXPENSE", category_id=None):
    payload = {
        "amount": amount,
        "description": notes,
        "date": spent_date.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"create expense failed: {r.get_json()}"
    return r.get_json()


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (200, 201), f"create category failed: {r.get_json()}"
    return r.get_json()


def _create_bill(client, auth_header, *, name, amount, next_due_date, cadence="MONTHLY"):
    r = client.post(
        "/bills",
        json={
            "name": name,
            "amount": amount,
            "next_due_date": next_due_date.isoformat(),
            "cadence": cadence,
        },
        headers=auth_header,
    )
    assert r.status_code in (200, 201), f"create bill failed: {r.get_json()}"
    return r.get_json()


# ── Weekly Digest Tests ──────────────────────────────────────────────


class TestWeeklyDigest:
    def test_returns_200_with_no_data(self, client, auth_header):
        """Digest should return successfully even when user has no expenses."""
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "period" in data
        assert "summary" in data
        assert "categories" in data
        assert "daily_spending" in data
        assert "narrative" in data
        assert data["summary"]["total_spent"] == 0.0
        assert data["summary"]["transaction_count"] == 0

    def test_digest_includes_current_week_spending(self, client, auth_header):
        """Expenses in the current week should be reflected in the digest."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=50, spent_date=monday)
        _create_expense(client, auth_header, amount=30, spent_date=monday + timedelta(days=1))

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["total_spent"] == 80.0
        assert data["summary"]["transaction_count"] == 2

    def test_digest_calculates_daily_average(self, client, auth_header):
        """Daily average should be total / 7."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=70, spent_date=monday)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["summary"]["daily_average"] == 10.0  # 70 / 7

    def test_digest_includes_income_in_net_flow(self, client, auth_header):
        """Net flow = income - expenses for the week."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=100, spent_date=monday, expense_type="INCOME")
        _create_expense(client, auth_header, amount=40, spent_date=monday)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["summary"]["total_income"] == 100.0
        assert data["summary"]["total_spent"] == 40.0
        assert data["summary"]["net_flow"] == 60.0

    def test_digest_category_breakdown(self, client, auth_header):
        """Category breakdown should sum expenses per category."""
        monday = _monday_of_current_week()
        cat = _create_category(client, auth_header, "Food")
        cat_id = cat["id"]
        _create_expense(client, auth_header, amount=25, spent_date=monday, category_id=cat_id)
        _create_expense(client, auth_header, amount=15, spent_date=monday + timedelta(days=1), category_id=cat_id)
        _create_expense(client, auth_header, amount=10, spent_date=monday)  # Uncategorized

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        categories = data["categories"]
        assert len(categories) == 2
        food_cat = next(c for c in categories if c["category_name"] == "Food")
        assert food_cat["amount"] == 40.0
        assert food_cat["transaction_count"] == 2

    def test_wow_change_percentage(self, client, auth_header):
        """Week-over-week change should compare current vs previous week."""
        monday = _monday_of_current_week()
        prev_monday = monday - timedelta(weeks=1)

        # Previous week: spend 100
        _create_expense(client, auth_header, amount=100, spent_date=prev_monday)
        # Current week: spend 150
        _create_expense(client, auth_header, amount=150, spent_date=monday)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["summary"]["wow_change_pct"] == 50.0  # (150-100)/100 * 100

    def test_wow_change_null_when_no_data_both_weeks(self, client, auth_header):
        """If no spending in either week, wow_change should be None."""
        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["summary"]["wow_change_pct"] is None

    def test_week_offset_parameter(self, client, auth_header):
        """week_offset=-1 should return last week's digest."""
        prev_monday = _monday_of_current_week() - timedelta(weeks=1)
        _create_expense(client, auth_header, amount=200, spent_date=prev_monday)

        r = client.get("/digest/weekly?week_offset=-1", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["period"]["week_offset"] == -1
        assert data["summary"]["total_spent"] == 200.0

    def test_invalid_week_offset_returns_400(self, client, auth_header):
        r = client.get("/digest/weekly?week_offset=abc", headers=auth_header)
        assert r.status_code == 400

    def test_positive_week_offset_returns_400(self, client, auth_header):
        r = client.get("/digest/weekly?week_offset=1", headers=auth_header)
        assert r.status_code == 400

    def test_extreme_week_offset_returns_400(self, client, auth_header):
        r = client.get("/digest/weekly?week_offset=-100", headers=auth_header)
        assert r.status_code == 400

    def test_unauthenticated_returns_401(self, client):
        r = client.get("/digest/weekly")
        assert r.status_code in (401, 422)

    def test_narrative_present(self, client, auth_header):
        """Every digest should have a narrative (heuristic fallback if no AI)."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=50, spent_date=monday)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert "narrative" in data
        assert data["narrative_method"] == "heuristic"
        assert len(data["narrative"]) > 0

    def test_spikes_detected(self, client, auth_header):
        """Spending spike detection when category doubles vs last week."""
        monday = _monday_of_current_week()
        prev_monday = monday - timedelta(weeks=1)
        cat = _create_category(client, auth_header, "Shopping")
        cat_id = cat["id"]

        # Previous week: 50
        _create_expense(client, auth_header, amount=50, spent_date=prev_monday, category_id=cat_id)
        # Current week: 120 (140% increase)
        _create_expense(client, auth_header, amount=120, spent_date=monday, category_id=cat_id)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert len(data["spikes"]) > 0
        spike = data["spikes"][0]
        assert spike["category_name"] == "Shopping"
        assert spike["current_amount"] == 120.0
        assert spike["previous_amount"] == 50.0
        assert spike["increase_pct"] == 140.0

    def test_savings_opportunities_present(self, client, auth_header):
        """Savings opportunities should be generated when there's spending."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=100, spent_date=monday)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert "savings_opportunities" in data
        assert len(data["savings_opportunities"]) > 0

    def test_daily_spending_breakdown(self, client, auth_header):
        """Daily spending should have one entry per day with spending."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=20, spent_date=monday)
        _create_expense(client, auth_header, amount=30, spent_date=monday + timedelta(days=2))

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert len(data["daily_spending"]) == 2
        assert data["daily_spending"][0]["date"] == monday.isoformat()
        assert data["daily_spending"][0]["amount"] == 20.0

    def test_bills_section(self, client, auth_header):
        """Bills due within 14 days should appear in the digest."""
        due_date = date.today() + timedelta(days=5)
        _create_bill(client, auth_header, name="Netflix", amount=15.99, next_due_date=due_date)

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert len(data["bills"]["upcoming"]) == 1
        assert data["bills"]["upcoming"][0]["name"] == "Netflix"
        assert data["bills"]["upcoming_total"] == 15.99

    def test_ai_narrative_used_when_available(self, client, auth_header, monkeypatch):
        """When AI service returns text, narrative_method should be 'ai'."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=50, spent_date=monday)

        monkeypatch.setattr(
            "app.services.digest._generate_ai_narrative",
            lambda *a, **kw: "AI-generated summary of your spending.",
        )

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["narrative_method"] == "ai"
        assert data["narrative"] == "AI-generated summary of your spending."

    def test_ai_fallback_on_failure(self, client, auth_header, monkeypatch):
        """When AI fails, heuristic narrative should be used."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=50, spent_date=monday)

        monkeypatch.setattr(
            "app.services.digest._generate_ai_narrative",
            lambda *a, **kw: None,
        )

        r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["narrative_method"] == "heuristic"
        assert len(data["narrative"]) > 0


# ── Trends Tests ─────────────────────────────────────────────────────


class TestSpendingTrends:
    def test_returns_200_with_no_data(self, client, auth_header):
        r = client.get("/digest/trends", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "weekly_totals" in data
        assert "category_trends" in data
        assert data["weeks_included"] == 8

    def test_custom_weeks_parameter(self, client, auth_header):
        r = client.get("/digest/trends?weeks=4", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["weeks_included"] == 4
        assert len(data["weekly_totals"]) == 4

    def test_invalid_weeks_returns_400(self, client, auth_header):
        r = client.get("/digest/trends?weeks=abc", headers=auth_header)
        assert r.status_code == 400

    def test_weeks_out_of_range_returns_400(self, client, auth_header):
        r = client.get("/digest/trends?weeks=1", headers=auth_header)
        assert r.status_code == 400
        r = client.get("/digest/trends?weeks=20", headers=auth_header)
        assert r.status_code == 400

    def test_weekly_totals_include_spending(self, client, auth_header):
        """Spending should appear in the correct week."""
        monday = _monday_of_current_week()
        _create_expense(client, auth_header, amount=99, spent_date=monday)

        r = client.get("/digest/trends?weeks=4", headers=auth_header)
        data = r.get_json()
        # Current week should be the last entry (chronological order)
        current_week = data["weekly_totals"][-1]
        assert current_week["total_spent"] == 99.0

    def test_category_trends_include_trend_direction(self, client, auth_header):
        """Category trends should have a trend direction."""
        monday = _monday_of_current_week()
        cat = _create_category(client, auth_header, "Food")
        cat_id = cat["id"]

        # Increasing trend: more spending each week
        for i in range(4):
            spent_date = monday - timedelta(weeks=3 - i)
            amount = 10 * (i + 1)  # 10, 20, 30, 40
            _create_expense(
                client, auth_header,
                amount=amount,
                spent_date=spent_date,
                category_id=cat_id,
            )

        r = client.get("/digest/trends?weeks=4", headers=auth_header)
        data = r.get_json()
        assert len(data["category_trends"]) > 0
        food_trend = next(
            (t for t in data["category_trends"] if t["category_name"] == "Food"),
            None,
        )
        assert food_trend is not None
        assert food_trend["trend"] == "increasing"

    def test_unauthenticated_returns_401(self, client):
        r = client.get("/digest/trends")
        assert r.status_code in (401, 422)

    def test_weekly_totals_chronological_order(self, client, auth_header):
        """Weekly totals should be in chronological order (oldest first)."""
        r = client.get("/digest/trends?weeks=4", headers=auth_header)
        data = r.get_json()
        dates = [w["week_start"] for w in data["weekly_totals"]]
        assert dates == sorted(dates)


# ── Service Unit Tests ───────────────────────────────────────────────


class TestDigestServiceHelpers:
    def test_trend_direction_increasing(self):
        from app.services.digest import _trend_direction

        assert _trend_direction([10, 20, 30, 40]) == "increasing"

    def test_trend_direction_decreasing(self):
        from app.services.digest import _trend_direction

        assert _trend_direction([40, 30, 20, 10]) == "decreasing"

    def test_trend_direction_stable(self):
        from app.services.digest import _trend_direction

        assert _trend_direction([10, 10, 10, 10]) == "stable"

    def test_trend_direction_single_value(self):
        from app.services.digest import _trend_direction

        assert _trend_direction([10]) == "stable"

    def test_trend_direction_empty(self):
        from app.services.digest import _trend_direction

        assert _trend_direction([]) == "stable"

    def test_week_bounds_current(self):
        from app.services.digest import _week_bounds

        monday, sunday = _week_bounds(0)
        today = date.today()
        assert monday.weekday() == 0  # Monday
        assert sunday.weekday() == 6  # Sunday
        assert monday <= today <= sunday

    def test_week_bounds_previous(self):
        from app.services.digest import _week_bounds

        monday, sunday = _week_bounds(-1)
        assert monday.weekday() == 0
        assert sunday.weekday() == 6
        assert sunday < date.today()

    def test_detect_spikes_identifies_increase(self):
        from app.services.digest import _detect_spikes

        current = [{"category_name": "Food", "amount": 200}]
        prev = [{"category_name": "Food", "amount": 100}]
        spikes = _detect_spikes(current, prev, threshold=1.5)
        assert len(spikes) == 1
        assert spikes[0]["increase_pct"] == 100.0

    def test_detect_spikes_no_spike_below_threshold(self):
        from app.services.digest import _detect_spikes

        current = [{"category_name": "Food", "amount": 110}]
        prev = [{"category_name": "Food", "amount": 100}]
        spikes = _detect_spikes(current, prev, threshold=1.5)
        assert len(spikes) == 0

    def test_detect_spikes_new_category(self):
        from app.services.digest import _detect_spikes

        current = [{"category_name": "Gym", "amount": 50}]
        prev = []
        spikes = _detect_spikes(current, prev, threshold=1.5)
        assert len(spikes) == 1
        assert spikes[0]["increase_pct"] is None  # new category

    def test_heuristic_narrative_with_data(self, app_fixture):
        from app.services.digest import _heuristic_narrative

        digest_data = {
            "period": {"start": "2025-03-10", "end": "2025-03-16"},
            "summary": {
                "total_spent": 500.0,
                "wow_change_pct": -15.0,
                "transaction_count": 12,
            },
            "categories": [
                {"category_name": "Food", "share_pct": 45.0, "amount": 225},
            ],
            "bills": {"upcoming": [1, 2], "overdue": []},
        }
        narrative = _heuristic_narrative(digest_data)
        assert "500.00" in narrative
        assert "decreased" in narrative.lower()
        assert "Food" in narrative

    def test_heuristic_narrative_empty_data(self, app_fixture):
        from app.services.digest import _heuristic_narrative

        digest_data = {
            "period": {"start": "2025-03-10", "end": "2025-03-16"},
            "summary": {
                "total_spent": 0.0,
                "wow_change_pct": None,
                "transaction_count": 0,
            },
            "categories": [],
            "bills": {"upcoming": [], "overdue": []},
        }
        narrative = _heuristic_narrative(digest_data)
        assert "0.00" in narrative
        assert "0 transactions" in narrative
