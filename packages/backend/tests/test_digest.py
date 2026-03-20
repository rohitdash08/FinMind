"""Tests for the weekly financial digest feature."""

from datetime import date, timedelta

import pytest

from app.services.digest import (
    week_bounds,
    previous_week,
    parse_week_string,
    current_week_string,
    _heuristic_insights,
)


# ---------------------------------------------------------------------------
# Unit tests for date helpers
# ---------------------------------------------------------------------------


class TestWeekBounds:
    def test_known_week(self):
        monday, sunday = week_bounds(2026, 12)
        assert monday.isoweekday() == 1  # Monday
        assert sunday.isoweekday() == 7  # Sunday
        assert (sunday - monday).days == 6

    def test_week_1(self):
        monday, sunday = week_bounds(2026, 1)
        assert monday.isoweekday() == 1
        assert (sunday - monday).days == 6

    def test_last_week_of_year(self):
        monday, sunday = week_bounds(2025, 52)
        assert monday.isoweekday() == 1
        assert (sunday - monday).days == 6


class TestPreviousWeek:
    def test_mid_year(self):
        y, w = previous_week(2026, 12)
        assert (y, w) == (2026, 11)

    def test_week_1_wraps_to_previous_year(self):
        y, w = previous_week(2026, 1)
        assert y == 2025
        assert w >= 52


class TestParseWeekString:
    def test_valid(self):
        assert parse_week_string("2026-W12") == (2026, 12)
        assert parse_week_string("2025-W01") == (2025, 1)

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_week_string("2026-12")
        with pytest.raises(ValueError):
            parse_week_string("bad")


class TestCurrentWeekString:
    def test_format(self):
        result = current_week_string()
        assert result.startswith("20")
        assert "-W" in result


# ---------------------------------------------------------------------------
# Unit tests for heuristic insights
# ---------------------------------------------------------------------------


class TestHeuristicInsights:
    def test_negative_cash_flow(self):
        tips = _heuristic_insights(
            income=100,
            expenses=200,
            trends={"expense_change_pct": 0},
            categories=[{"category_name": "Food", "share_pct": 60}],
        )
        assert any("more than you earned" in t for t in tips)

    def test_positive_cash_flow(self):
        tips = _heuristic_insights(
            income=500,
            expenses=200,
            trends={"expense_change_pct": 0},
            categories=[{"category_name": "Transport", "share_pct": 40}],
        )
        assert any("Positive cash flow" in t for t in tips)

    def test_spending_spike(self):
        tips = _heuristic_insights(
            income=500,
            expenses=500,
            trends={"expense_change_pct": 50},
            categories=[],
        )
        assert any("jumped" in t for t in tips)

    def test_spending_drop(self):
        tips = _heuristic_insights(
            income=500,
            expenses=200,
            trends={"expense_change_pct": -30},
            categories=[],
        )
        assert any("discipline" in t.lower() or "dropped" in t.lower() for t in tips)

    def test_max_five_tips(self):
        tips = _heuristic_insights(
            income=100,
            expenses=500,
            trends={"expense_change_pct": 50},
            categories=[
                {"category_name": "A", "share_pct": 50},
                {"category_name": "B", "share_pct": 30},
            ],
        )
        assert len(tips) <= 5


# ---------------------------------------------------------------------------
# Integration tests (with Flask test client)
# ---------------------------------------------------------------------------


class TestWeeklyDigestEndpoint:
    def test_returns_digest_structure(self, client, auth_header):
        today = date.today()
        y, w, _ = today.isocalendar()
        week_str = f"{y}-W{w:02d}"

        # Add an expense this week
        monday, _ = week_bounds(y, w)
        r = client.post(
            "/expenses",
            json={
                "amount": 42.50,
                "description": "Coffee and lunch",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        # Add income this week
        r = client.post(
            "/expenses",
            json={
                "amount": 200,
                "description": "Freelance payment",
                "date": monday.isoformat(),
                "expense_type": "INCOME",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        # Get digest
        r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()

        # Verify structure
        assert payload["week"] == week_str
        assert "period" in payload
        assert payload["period"]["start"] == monday.isoformat()

        assert "summary" in payload
        summary = payload["summary"]
        assert summary["total_income"] == 200.0
        assert summary["total_expenses"] == 42.50
        assert summary["net_flow"] == 157.50
        assert summary["transaction_count"] == 2

        assert "trends" in payload
        assert "category_breakdown" in payload
        assert "daily_spending" in payload
        assert "transactions" in payload
        assert "insights" in payload
        assert isinstance(payload["insights"], list)
        assert payload["method"] == "heuristic"

    def test_defaults_to_current_week(self, client, auth_header):
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        today = date.today()
        y, w, _ = today.isocalendar()
        assert payload["week"] == f"{y}-W{w:02d}"

    def test_invalid_week_format(self, client, auth_header):
        r = client.get("/digest/weekly?week=bad-format", headers=auth_header)
        assert r.status_code == 400
        assert "error" in r.get_json()

    def test_empty_week(self, client, auth_header):
        r = client.get("/digest/weekly?week=2020-W01", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["summary"]["total_income"] == 0.0
        assert payload["summary"]["total_expenses"] == 0.0
        assert payload["summary"]["net_flow"] == 0.0
        assert payload["summary"]["transaction_count"] == 0

    def test_trends_with_previous_week_data(self, client, auth_header):
        today = date.today()
        y, w, _ = today.isocalendar()
        monday, _ = week_bounds(y, w)

        # Previous week expense
        prev_monday = monday - timedelta(days=7)
        r = client.post(
            "/expenses",
            json={
                "amount": 100,
                "description": "Last week expense",
                "date": prev_monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        # This week expense
        r = client.post(
            "/expenses",
            json={
                "amount": 150,
                "description": "This week expense",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        week_str = f"{y}-W{w:02d}"
        r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()

        trends = payload["trends"]
        assert "previous_week" in trends
        assert trends["previous_expenses"] == 100.0
        assert trends["expense_change_pct"] == 50.0  # 150 vs 100

    def test_gemini_fallback(self, client, auth_header, monkeypatch):
        def _boom(*_args, **_kwargs):
            raise RuntimeError("gemini down")

        monkeypatch.setattr(
            "app.services.digest._gemini_digest_insights", _boom
        )

        r = client.get(
            "/digest/weekly",
            headers={
                **auth_header,
                "X-Gemini-Api-Key": "fake-key",
            },
        )
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["method"] == "heuristic"
        assert "warnings" in payload
        assert "gemini_unavailable" in payload["warnings"]

    def test_gemini_integration(self, client, auth_header, monkeypatch):
        captured = {}

        def _fake_gemini(income, expenses, trends, categories, daily, api_key, model, persona):
            captured["api_key"] = api_key
            return ["Insight 1", "Insight 2", "Insight 3"]

        monkeypatch.setattr(
            "app.services.digest._gemini_digest_insights", _fake_gemini
        )

        r = client.get(
            "/digest/weekly",
            headers={
                **auth_header,
                "X-Gemini-Api-Key": "user-key-123",
            },
        )
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["method"] == "gemini"
        assert payload["insights"] == ["Insight 1", "Insight 2", "Insight 3"]
        assert captured["api_key"] == "user-key-123"

    def test_requires_auth(self, client):
        r = client.get("/digest/weekly")
        assert r.status_code in (401, 422)

    def test_category_breakdown_in_digest(self, client, auth_header):
        today = date.today()
        y, w, _ = today.isocalendar()
        monday, _ = week_bounds(y, w)

        # Add categorized expense
        r = client.post(
            "/expenses",
            json={
                "amount": 75,
                "description": "Groceries",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        week_str = f"{y}-W{w:02d}"
        r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()

        assert len(payload["category_breakdown"]) >= 1
        assert payload["category_breakdown"][0]["amount"] == 75.0

    def test_daily_spending_in_digest(self, client, auth_header):
        today = date.today()
        y, w, _ = today.isocalendar()
        monday, _ = week_bounds(y, w)

        r = client.post(
            "/expenses",
            json={
                "amount": 30,
                "description": "Day 1 expense",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        tuesday = monday + timedelta(days=1)
        r = client.post(
            "/expenses",
            json={
                "amount": 45,
                "description": "Day 2 expense",
                "date": tuesday.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

        week_str = f"{y}-W{w:02d}"
        r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()

        daily = payload["daily_spending"]
        assert len(daily) == 2
        amounts = [d["amount"] for d in daily]
        assert 30.0 in amounts
        assert 45.0 in amounts
